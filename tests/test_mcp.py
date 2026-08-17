import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import os
import re
import unittest

SOURCE_DIR = Path(__file__).parents[1] / "src/opnsense/scripts/OPNsense/WanQuota"
sys.path.insert(0, str(SOURCE_DIR))
SPEC = importlib.util.spec_from_file_location("wanquota_mcp", SOURCE_DIR / "mcp.py")
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


def request(method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


class HandshakeTests(unittest.TestCase):
    def test_initialize_agrees_to_a_supported_protocol_version(self):
        response = MCP.handle(request("initialize", {"protocolVersion": "2025-06-18"}))
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(response["result"]["serverInfo"]["name"], "wanquota")

    def test_initialize_does_not_claim_an_unsupported_protocol_version(self):
        # Echoing whatever the client asked for advertised revisions that were
        # never implemented, and a client would negotiate on that false premise.
        response = MCP.handle(request("initialize", {"protocolVersion": "1999-01-01"}))
        self.assertEqual(response["result"]["protocolVersion"], MCP.PROTOCOL_VERSION)
        self.assertIn(response["result"]["protocolVersion"], MCP.SUPPORTED_PROTOCOL_VERSIONS)

    def test_initialize_falls_back_to_default_version(self):
        response = MCP.handle(request("initialize", {}))
        self.assertEqual(response["result"]["protocolVersion"], MCP.PROTOCOL_VERSION)

    def test_initialized_notification_returns_nothing(self):
        self.assertIsNone(MCP.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_is_method_not_found(self):
        response = MCP.handle(request("does/not/exist"))
        self.assertEqual(response["error"]["code"], MCP.METHOD_NOT_FOUND)

    def test_unknown_notification_is_silently_ignored(self):
        self.assertIsNone(MCP.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"}))

    def test_non_jsonrpc_payload_is_invalid_request(self):
        response = MCP.handle({"method": "tools/list"})
        self.assertEqual(response["error"]["code"], MCP.INVALID_REQUEST)

    def test_malformed_json_is_parse_error(self):
        response = MCP.handle_raw("{not json")
        self.assertEqual(response["error"]["code"], MCP.PARSE_ERROR)


class ToolSurfaceTests(unittest.TestCase):
    def test_tools_list_is_advertised_with_schemas(self):
        response = MCP.handle(request("tools/list"))
        tools = response["result"]["tools"]
        self.assertEqual(len(tools), len(MCP.TOOLS))
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")

    # The tools that may change configuration. The server was read-only until the
    # owner asked for full control, so this list is the boundary: a tool that writes
    # has to be named here deliberately, and anything not named must still declare
    # itself read-only. That keeps "which of these can change my firewall?" a
    # question with an answer in one place.
    WRITERS = {
        "wanquota_set_settings",
        "wanquota_set_service_limit",
        "wanquota_remove_service_limit",
        "wanquota_set_device_limit",
        "wanquota_remove_device_limit",
        "wanquota_decide_service",
    }
    REMOVERS = {"wanquota_remove_service_limit", "wanquota_remove_device_limit"}

    def test_only_the_declared_writers_are_not_read_only(self):
        for tool in MCP.handle(request("tools/list"))["result"]["tools"]:
            name = tool["name"]
            expected = name not in self.WRITERS
            self.assertEqual(tool["annotations"]["readOnlyHint"], expected, name)
            self.assertTrue(tool["annotations"]["title"], name)

    def test_removing_a_limit_is_flagged_destructive(self):
        # A client should be able to prompt before discarding something the user set,
        # and not prompt for a report.
        for tool in MCP.handle(request("tools/list"))["result"]["tools"]:
            self.assertEqual(tool["annotations"]["destructiveHint"],
                             tool["name"] in self.REMOVERS, tool["name"])

    def test_every_writer_exists_on_the_surface(self):
        names = {tool["name"] for tool in MCP.tool_descriptors()}
        for writer in self.WRITERS:
            self.assertIn(writer, names)

    def test_no_argument_schemas_survive_as_objects(self):
        # These serialise to {} and a transport that turns them into [] breaks
        # every client; keep the shape asserted at the source.
        for tool in MCP.handle(request("tools/list"))["result"]["tools"]:
            self.assertIsInstance(tool["inputSchema"]["properties"], dict, tool["name"])

    def test_routing_guardrails_stay_off_the_tool_surface(self):
        # Limits and settings are now writable, but the guardrail that changes
        # routing is not: shaping traffic is recoverable, moving a household onto a
        # different WAN is a decision with a bill attached.
        names = {tool["name"] for tool in MCP.tool_descriptors()}
        self.assertNotIn("wanquota_override", names)
        self.assertFalse(any("override" in name or "enforce" in name for name in names))

    def test_no_tool_can_reach_per_device_enforcement(self):
        # devices.py can block a device off the network. Nothing on the MCP
        # surface may reach it, and no resource may either.
        forbidden = ("enforce", "block", "budget_apply", "devices_apply", "flush")
        names = {tool["name"] for tool in MCP.tool_descriptors()}
        for word in forbidden:
            self.assertFalse(any(word in name for name in names), word)
        for uri in MCP.RESOURCES_BY_URI:
            self.assertFalse(any(word in uri for word in forbidden), uri)

    def test_handlers_do_not_import_the_enforcement_module(self):
        import sys as _sys
        self.assertNotIn("devices", {m.split(".")[-1] for m in _sys.modules
                                     if m.startswith("wanquota_mcp")})

    def test_unknown_tool_is_method_not_found(self):
        response = MCP.handle(request("tools/call", {"name": "nope", "arguments": {}}))
        self.assertEqual(response["error"]["code"], MCP.METHOD_NOT_FOUND)

    def test_invalid_period_is_invalid_params(self):
        response = MCP.handle(request("tools/call", {
            "name": "wanquota_consumers",
            "arguments": {"period": "fortnight"},
        }))
        self.assertEqual(response["error"]["code"], MCP.INVALID_PARAMS)

    def test_period_defaults_to_thirty(self):
        self.assertEqual(MCP._period({}), "thirty")
        self.assertEqual(MCP._period({"period": "week"}), "week")


class CapabilityAndResourceTests(unittest.TestCase):
    def test_initialize_declares_resources(self):
        caps = MCP.handle(request("initialize", {}))["result"]["capabilities"]
        self.assertIn("tools", caps)
        self.assertIn("resources", caps)

    def test_resources_are_listed(self):
        uris = {r["uri"] for r in MCP.handle(request("resources/list"))["result"]["resources"]}
        self.assertEqual(uris, {"wanquota://summary", "wanquota://health"})

    def test_resource_descriptors_declare_a_mime_type(self):
        for r in MCP.handle(request("resources/list"))["result"]["resources"]:
            self.assertEqual(r["mimeType"], "application/json")

    def test_unknown_resource_is_invalid_params_and_lists_the_real_ones(self):
        response = MCP.handle(request("resources/read", {"uri": "wanquota://nope"}))
        self.assertEqual(response["error"]["code"], MCP.INVALID_PARAMS)
        self.assertIn("wanquota://summary", response["error"]["message"])

    def test_resource_read_returns_json_text(self):
        original = MCP.RESOURCES_BY_URI["wanquota://health"]["handler"]
        MCP.RESOURCES_BY_URI["wanquota://health"]["handler"] = lambda _a: {"status": "ok", "checks": []}
        try:
            body = MCP.handle(request("resources/read", {"uri": "wanquota://health"}))
            content = body["result"]["contents"][0]
            self.assertEqual(json.loads(content["text"])["status"], "ok")
            self.assertEqual(content["uri"], "wanquota://health")
        finally:
            MCP.RESOURCES_BY_URI["wanquota://health"]["handler"] = original

    def test_tools_with_an_output_schema_declare_it(self):
        declared = {t["name"] for t in MCP.tool_descriptors() if "outputSchema" in t}
        self.assertEqual(declared, {"wanquota_health", "wanquota_device",
                                    "wanquota_site", "wanquota_categories"})

    def test_limits_are_reportable_but_not_settable(self):
        self.assertIn("wanquota_limits", MCP.TOOLS_BY_NAME)
        names = {t["name"] for t in MCP.tool_descriptors()}
        # Reporting a limit is fine; changing one must stay out of the tool surface.
        for word in ("set_limit", "apply_limit", "limit_set", "shaper_apply"):
            self.assertFalse(any(word in name for name in names), word)
        self.assertTrue({t["name"]: t for t in MCP.tool_descriptors()}
                        ["wanquota_limits"]["annotations"]["readOnlyHint"])

    def test_apps_and_sessions_tools_exist_and_are_read_only(self):
        for name in ("wanquota_apps", "wanquota_sessions"):
            self.assertIn(name, MCP.TOOLS_BY_NAME)
        annotations = {t["name"]: t["annotations"] for t in MCP.tool_descriptors()}
        for name in ("wanquota_apps", "wanquota_sessions"):
            self.assertTrue(annotations[name]["readOnlyHint"])

    def test_the_category_drill_tool_exists_and_requires_a_category(self):
        self.assertIn("wanquota_category", MCP.TOOLS_BY_NAME)
        schema = MCP.TOOLS_BY_NAME["wanquota_category"]["inputSchema"]
        self.assertEqual(schema["required"], ["category"])

    def test_big_payload_tools_deliberately_declare_no_output_schema(self):
        # Left undeclared on purpose: an approximate schema a client enforces is
        # worse than none, because it rejects valid data.
        undeclared = {t["name"] for t in MCP.tool_descriptors() if "outputSchema" not in t}
        self.assertIn("wanquota_consumers", undeclared)
        self.assertIn("wanquota_intelligence", undeclared)


class ToolCallTests(unittest.TestCase):
    def setUp(self):
        self.original = {name: tool["handler"] for name, tool in MCP.TOOLS_BY_NAME.items()}

    def tearDown(self):
        for name, handler in self.original.items():
            MCP.TOOLS_BY_NAME[name]["handler"] = handler

    def test_successful_call_wraps_payload_as_json_text(self):
        MCP.TOOLS_BY_NAME["wanquota_summary"]["handler"] = lambda _a: {"status": "ok", "providers": []}
        response = MCP.handle(request("tools/call", {"name": "wanquota_summary", "arguments": {}}))
        self.assertFalse(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "ok")

    def test_arguments_are_optional(self):
        MCP.TOOLS_BY_NAME["wanquota_summary"]["handler"] = lambda _a: {"status": "ok"}
        response = MCP.handle(request("tools/call", {"name": "wanquota_summary"}))
        self.assertFalse(response["result"]["isError"])

    def test_collector_failure_is_reported_without_killing_the_session(self):
        def explode(_arguments):
            raise OSError("vnstat database missing")

        MCP.TOOLS_BY_NAME["wanquota_health"]["handler"] = explode
        response = MCP.handle(request("tools/call", {"name": "wanquota_health", "arguments": {}}))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("vnstat database missing", response["result"]["content"][0]["text"])

    def test_keyerror_inside_a_tool_is_not_reported_as_unknown_tool(self):
        # KeyError is a LookupError; catching LookupError broadly would blame the
        # caller for a missing settings key.
        def explode(_arguments):
            raise KeyError("domain_enabled")

        MCP.TOOLS_BY_NAME["wanquota_consumers"]["handler"] = explode
        response = MCP.handle(request("tools/call", {
            "name": "wanquota_consumers", "arguments": {"period": "week"},
        }))
        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("KeyError", response["result"]["content"][0]["text"])

    def test_valueerror_inside_a_tool_is_not_reported_as_invalid_params(self):
        def explode(_arguments):
            raise ValueError("invalid literal for int() with base 10: ''")

        MCP.TOOLS_BY_NAME["wanquota_summary"]["handler"] = explode
        response = MCP.handle(request("tools/call", {"name": "wanquota_summary", "arguments": {}}))
        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("ValueError", response["result"]["content"][0]["text"])


SAMPLE_CONSUMERS = {
    "status": "ok",
    "period": "thirty",
    "hosts": [
        {"ip": "192.0.2.10", "name": "TRUENAS", "download": 900, "upload": 100, "total": 1000},
        {"ip": "192.0.2.11", "name": "Quiet Box", "download": 5, "upload": 0, "total": 5},
    ],
    "domains": [{"domain": "cdn.example", "total": 700, "ip_count": 3}],
    "device_domains": [
        {"device": "192.0.2.10", "name": "TRUENAS", "domain": "cdn.example", "total": 600},
        {"device": "192.0.2.10", "name": "TRUENAS", "domain": "pkg.example", "total": 200},
        {"device": "192.0.2.12", "name": "Laptop", "domain": "cdn.example", "total": 100},
    ],
    "device_attribution": [
        {"device": "192.0.2.10", "name": "TRUENAS", "external": 1000, "attributed": 800,
         "unattributed": 200, "coverage_percent": 80.0, "likely_unattributable": False},
    ],
    "providers": [
        {"name": "ETISALAT", "interface": "igb0",
         "devices": [{"ip": "192.0.2.10", "name": "TRUENAS", "total": 400}],
         "domains": [{"domain": "cdn.example", "total": 350}]},
    ],
}


class DrillToolTests(unittest.TestCase):
    def setUp(self):
        self.original = MCP.consumers.report
        MCP.consumers.report = lambda _period: SAMPLE_CONSUMERS

    def tearDown(self):
        MCP.consumers.report = self.original

    def call(self, name, arguments):
        return MCP.handle(request("tools/call", {"name": name, "arguments": arguments}))

    @staticmethod
    def payload(response):
        return json.loads(response["result"]["content"][0]["text"])

    def test_device_by_name_is_case_insensitive(self):
        body = self.payload(self.call("wanquota_device", {"device": "truenas"}))
        self.assertEqual(body["device"], "192.0.2.10")
        self.assertEqual([s["domain"] for s in body["sites"]], ["cdn.example", "pkg.example"])

    def test_device_by_ip(self):
        body = self.payload(self.call("wanquota_device", {"device": "192.0.2.10"}))
        self.assertEqual(body["name"], "TRUENAS")
        self.assertEqual(body["attribution"]["coverage_percent"], 80.0)

    def test_device_reports_carrying_providers(self):
        body = self.payload(self.call("wanquota_device", {"device": "TRUENAS"}))
        self.assertEqual(body["providers"], [{"name": "ETISALAT", "total": 400}])

    def test_device_known_only_from_rrd_returns_empty_sites(self):
        body = self.payload(self.call("wanquota_device", {"device": "Quiet Box"}))
        self.assertEqual(body["sites"], [])
        self.assertEqual(body["device_total"], 5)

    def test_unknown_device_is_invalid_params(self):
        response = self.call("wanquota_device", {"device": "nosuchbox"})
        self.assertEqual(response["error"]["code"], MCP.INVALID_PARAMS)

    def test_device_is_required(self):
        response = self.call("wanquota_device", {})
        self.assertEqual(response["error"]["code"], MCP.INVALID_PARAMS)

    def test_device_response_is_smaller_than_the_full_report(self):
        body = self.payload(self.call("wanquota_device", {"device": "TRUENAS"}))
        self.assertLess(len(json.dumps(body)), len(json.dumps(SAMPLE_CONSUMERS)))

    def test_site_lists_devices_ranked(self):
        body = self.payload(self.call("wanquota_site", {"site": "cdn.example"}))
        self.assertEqual([d["name"] for d in body["devices"]], ["TRUENAS", "Laptop"])
        self.assertEqual(body["total"], 700)
        self.assertEqual(body["observed_ip_count"], 3)

    def test_site_is_case_and_dot_insensitive(self):
        body = self.payload(self.call("wanquota_site", {"site": "CDN.Example."}))
        self.assertEqual(body["site"], "cdn.example")

    def test_unknown_site_returns_an_empty_result_not_an_error(self):
        # Mirrors wanquota_device, which returns a result for a device with no
        # attributable flow. "Nobody visited it" is an answer, and the server
        # cannot tell a typo from a real but unvisited domain.
        body = self.payload(self.call("wanquota_site", {"site": "nowhere.example"}))
        self.assertFalse(body["found"])
        self.assertEqual(body["devices"], [])
        self.assertIn("misspelled", body["empty_reason"])

    def test_known_site_is_marked_found(self):
        body = self.payload(self.call("wanquota_site", {"site": "cdn.example"}))
        self.assertTrue(body["found"])
        self.assertIsNone(body["empty_reason"])

    def test_wrong_argument_type_is_not_reported_as_missing(self):
        response = self.call("wanquota_device", {"device": 123})
        self.assertEqual(response["error"]["code"], MCP.INVALID_PARAMS)
        self.assertIn("must be a string", response["error"]["message"])

    def test_empty_argument_is_distinguished_from_missing(self):
        self.assertIn("must not be empty",
                      self.call("wanquota_device", {"device": "  "})["error"]["message"])
        self.assertIn("is required",
                      self.call("wanquota_device", {})["error"]["message"])

    def test_unknown_device_names_the_busiest_not_the_alphabetical_first(self):
        response = self.call("wanquota_device", {"device": "nosuchbox"})
        message = response["error"]["message"]
        # TRUENAS is the largest consumer; an alphabetical cut would drop it.
        self.assertIn("TRUENAS", message)
        self.assertIn("Busiest known devices", message)

    def test_device_note_covers_both_directions(self):
        body = self.payload(self.call("wanquota_device", {"device": "TRUENAS"}))
        self.assertIn("either can be the larger", body["note"])

    def test_device_with_no_sites_explains_why(self):
        body = self.payload(self.call("wanquota_device", {"device": "Quiet Box"}))
        self.assertEqual(body["sites"], [])
        self.assertIn("daily buckets", body["empty_reason"])

    def test_output_schema_tools_return_structured_content(self):
        response = self.call("wanquota_device", {"device": "TRUENAS"})
        self.assertIn("structuredContent", response["result"])
        self.assertEqual(response["result"]["structuredContent"]["name"], "TRUENAS")

    def test_tools_without_an_output_schema_omit_structured_content(self):
        MCP.TOOLS_BY_NAME["wanquota_consumers"]["handler"] = lambda _a: {"status": "ok"}
        try:
            response = self.call("wanquota_consumers", {})
            self.assertNotIn("structuredContent", response["result"])
        finally:
            MCP.TOOLS_BY_NAME["wanquota_consumers"]["handler"] = MCP.tool_consumers

    def test_categories_tool_returns_shares(self):
        original = MCP.intelligence.options
        MCP.intelligence.options = lambda: {"categories": MCP.intelligence.BUILTIN_CATEGORIES}
        MCP.TOOLS_BY_NAME["wanquota_consumers"]["handler"] = lambda _a: SAMPLE_CONSUMERS
        try:
            MCP.consumers.report = lambda _p: {
                "status": "ok",
                "domains": [{"domain": "youtube.com", "total": 900},
                            {"domain": "zoom.us", "total": 100}],
            }
            body = self.payload(self.call("wanquota_categories", {"period": "week"}))
            names = {c["name"]: c["percent"] for c in body["categories"]}
            self.assertAlmostEqual(names["Media Streaming"], 90.0)
            self.assertEqual(body["period"], "week")
        finally:
            MCP.intelligence.options = original

    def test_drill_tools_are_read_only(self):
        """The drill-downs answer questions; they must not change anything."""
        for name in ("wanquota_device", "wanquota_site"):
            self.assertIn(name, MCP.TOOLS_BY_NAME)
            self.assertTrue(
                MCP.TOOLS_BY_NAME[name].get("annotations", MCP.READ_ONLY_ANNOTATIONS)
                ["readOnlyHint"], name)
        names = {t["name"] for t in MCP.tool_descriptors()}
        self.assertFalse(any("override" in n or "enforce" in n for n in names))


LAN_CONFIG = """<?xml version="1.0"?>
<opnsense>
  <interfaces>
    <lan>
      <if>igb1</if>
      <ipaddr>192.168.10.1</ipaddr>
      <subnet>24</subnet>
    </lan>
  </interfaces>
</opnsense>
"""


class LanOnlyTests(unittest.TestCase):
    def setUp(self):
        self.handle = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        self.handle.write(LAN_CONFIG)
        self.handle.close()
        self.config = self.handle.name

    def tearDown(self):
        Path(self.config).unlink(missing_ok=True)

    def test_lan_address_is_permitted(self):
        self.assertTrue(MCP.is_permitted("192.168.10.55", self.config))

    def test_loopback_is_permitted(self):
        self.assertTrue(MCP.is_permitted("127.0.0.1", self.config))

    def test_off_lan_private_address_is_refused(self):
        # A different internal VLAN is still not the LAN.
        self.assertFalse(MCP.is_permitted("10.8.0.4", self.config))

    def test_public_address_is_refused(self):
        self.assertFalse(MCP.is_permitted("203.0.113.9", self.config))

    def test_garbage_address_is_refused(self):
        self.assertFalse(MCP.is_permitted("not-an-ip", self.config))

    def test_missing_config_fails_closed(self):
        self.assertFalse(MCP.is_permitted("192.168.10.55", "/nonexistent/config.xml"))
        self.assertEqual(MCP.lan_networks("/nonexistent/config.xml"), [])

    def test_non_literal_address_fails_closed(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        handle.write(LAN_CONFIG.replace("192.168.10.1", "dhcp"))
        handle.close()
        try:
            self.assertEqual(MCP.lan_networks(handle.name), [])
            self.assertFalse(MCP.is_permitted("192.168.10.55", handle.name))
        finally:
            Path(handle.name).unlink(missing_ok=True)

    def test_ipv6_lan_client_is_permitted(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        handle.write(LAN_CONFIG.replace(
            "<subnet>24</subnet>",
            "<subnet>24</subnet><ipaddrv6>fd00:abcd::1</ipaddrv6><subnetv6>64</subnetv6>",
        ))
        handle.close()
        try:
            self.assertTrue(MCP.is_permitted("fd00:abcd::5", handle.name))
            self.assertTrue(MCP.is_permitted("192.168.10.55", handle.name))
            self.assertFalse(MCP.is_permitted("fd00:beef::5", handle.name))
        finally:
            Path(handle.name).unlink(missing_ok=True)

    def test_absent_client_is_treated_as_stdio_and_allowed(self):
        self.assertTrue(MCP.is_permitted(None, self.config))
        self.assertTrue(MCP.is_permitted("", self.config))

    def test_serve_once_refuses_off_lan_before_parsing_body(self):
        encoded = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        response = MCP.serve_once(encoded, "203.0.113.9", self.config)
        self.assertEqual(response["error"]["code"], MCP.NOT_PERMITTED)

    def test_serve_once_allows_lan_client(self):
        encoded = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        response = MCP.serve_once(encoded, "192.168.10.55", self.config)
        self.assertEqual(len(response["result"]["tools"]), len(MCP.TOOLS))

    def test_refusal_precedes_body_parsing(self):
        # Even a malformed body must be refused as off-LAN, not reported as a
        # parse error, so an off-LAN caller learns nothing about the endpoint.
        response = MCP.serve_once("!!not base64!!", "203.0.113.9", self.config)
        self.assertEqual(response["error"]["code"], MCP.NOT_PERMITTED)


class TransportTests(unittest.TestCase):
    def test_stdio_loop_answers_requests_and_skips_notifications(self):
        lines = "\n".join([
            json.dumps(request("initialize", {"protocolVersion": "2024-11-05"})),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            "",
            json.dumps(request("tools/list", request_id=2)),
        ])
        stdout = io.StringIO()
        MCP.serve_stdio(io.StringIO(lines), stdout)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2])

    def test_once_decodes_base64_request(self):
        encoded = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        response = MCP.serve_once(encoded)
        self.assertEqual(len(response["result"]["tools"]), len(MCP.TOOLS))

    def test_once_signals_a_notification_so_http_can_answer_202(self):
        encoded = base64.b64encode(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
        ).decode()
        self.assertEqual(MCP.serve_once(encoded), {"_notification": True})

    def test_once_does_not_signal_notification_for_a_real_request(self):
        encoded = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        self.assertNotIn("_notification", MCP.serve_once(encoded))

    def test_refused_client_is_not_mistaken_for_a_notification(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False)
        handle.write(LAN_CONFIG)
        handle.close()
        try:
            encoded = base64.b64encode(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
            ).decode()
            response = MCP.serve_once(encoded, "203.0.113.9", handle.name)
            self.assertNotIn("_notification", response)
            self.assertEqual(response["error"]["code"], MCP.NOT_PERMITTED)
        finally:
            Path(handle.name).unlink(missing_ok=True)

    def test_once_rejects_invalid_base64(self):
        response = MCP.serve_once("not base64 !!!")
        self.assertEqual(response["error"]["code"], MCP.PARSE_ERROR)

    def test_once_tolerates_wrapped_base64(self):
        # FreeBSD's b64encode wraps at 76 columns; the embedded newline must not
        # be read as a malformed request.
        raw = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        wrapped = "\n".join([raw[:40], raw[40:]]) + "\n"
        response = MCP.serve_once(wrapped)
        self.assertEqual(len(response["result"]["tools"]), len(MCP.TOOLS))


if __name__ == "__main__":
    unittest.main()


class WriteToolTests(unittest.TestCase):
    """The tools that change configuration.

    Each records the instruction it would hand to configure.php rather than running
    it, so argument handling is tested without writing to a real firewall. The PHP
    side does the validating, and these check that it is asked the right question.
    """

    def capture(self):
        seen = {}

        def runner(script, instruction):
            seen["script"] = script
            seen["instruction"] = instruction
            return {"status": "ok", "action": instruction.get("action")}

        return seen, runner

    def call(self, name, arguments, runner):
        original = MCP.configure
        try:
            MCP.configure = lambda instruction: runner(MCP.CONFIGURE_SCRIPT, instruction)
            return MCP.TOOLS_BY_NAME[name]["handler"](arguments)
        finally:
            MCP.configure = original

    def test_a_service_cap_by_preset(self):
        seen, runner = self.capture()
        result = self.call("wanquota_set_service_limit",
                           {"service": "youtube", "resolution": "480p", "enabled": True,
                            "dry_run": False}, runner)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(seen["instruction"]["action"], "set_service_limit")
        self.assertEqual(seen["instruction"]["service"], "youtube")
        self.assertEqual(seen["instruction"]["resolution"], "480p")
        self.assertIs(seen["instruction"]["enabled"], True)
        self.assertIs(seen["instruction"]["dry_run"], False)

    def test_a_service_cap_by_rate(self):
        seen, runner = self.capture()
        self.call("wanquota_set_service_limit", {"service": "netflix", "mbit": 5}, runner)
        self.assertEqual(seen["instruction"]["mbit"], 5)

    def test_an_unknown_service_is_refused_before_writing(self):
        seen, runner = self.capture()
        with self.assertRaises(MCP.InvalidParams):
            self.call("wanquota_set_service_limit",
                      {"service": "nosuchservice", "mbit": 5}, runner)
        self.assertEqual(seen, {}, "nothing may be written for an unknown service")

    def test_a_service_cap_with_no_rate_is_refused(self):
        seen, runner = self.capture()
        with self.assertRaises(MCP.InvalidParams):
            self.call("wanquota_set_service_limit", {"service": "youtube"}, runner)
        self.assertEqual(seen, {})

    def test_the_shaper_state_is_left_alone_when_not_given(self):
        """Recording a limit must not silently turn shaping on."""
        seen, runner = self.capture()
        self.call("wanquota_set_service_limit", {"service": "youtube", "mbit": 3}, runner)
        self.assertNotIn("enabled", seen["instruction"])
        self.assertNotIn("dry_run", seen["instruction"])

    def test_a_device_cap(self):
        seen, runner = self.capture()
        self.call("wanquota_set_device_limit",
                  {"device": "e0:8f:4c:8f:a8:d6", "mbit": 3, "upload_mbit": 1}, runner)
        self.assertEqual(seen["instruction"]["action"], "set_device_limit")
        self.assertEqual(seen["instruction"]["device"], "e0:8f:4c:8f:a8:d6")
        self.assertEqual(seen["instruction"]["mbit"], 3)
        self.assertEqual(seen["instruction"]["upload_mbit"], 1)

    def test_a_device_cap_needs_a_device_and_a_rate(self):
        for arguments in ({"mbit": 3}, {"device": "192.168.1.5"}):
            seen, runner = self.capture()
            with self.assertRaises(MCP.InvalidParams):
                self.call("wanquota_set_device_limit", arguments, runner)
            self.assertEqual(seen, {})

    def test_removals_pass_the_identifier_through(self):
        for name, key, value in (("wanquota_remove_service_limit", "service", "youtube"),
                                 ("wanquota_remove_device_limit", "device", "192.168.1.5")):
            seen, runner = self.capture()
            self.call(name, {key: value}, runner)
            self.assertEqual(seen["instruction"][key], value)
            self.assertTrue(seen["instruction"]["action"].startswith("remove_"))

    def test_settings_require_a_non_empty_object(self):
        for bad in ({}, {"fields": {}}, {"fields": "shaper_enabled=1"}):
            seen, runner = self.capture()
            with self.assertRaises(MCP.InvalidParams):
                self.call("wanquota_set_settings", bad, runner)
            self.assertEqual(seen, {})

    def test_settings_are_passed_through_unchanged(self):
        seen, runner = self.capture()
        self.call("wanquota_set_settings",
                  {"fields": {"shaper_enabled": True, "top_limit": 20}}, runner)
        self.assertEqual(seen["instruction"]["fields"],
                         {"shaper_enabled": True, "top_limit": 20})

    def test_the_credential_is_never_returned(self):
        import tempfile
        config = """<?xml version="1.0"?>
<opnsense><OPNsense><WanQuota><general>
  <enabled>1</enabled>
  <smtp_host>mail.example.invalid</smtp_host>
  <smtp_password>a-real-secret</smtp_password>
</general></WanQuota></OPNsense></opnsense>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
            handle.write(config)
            path = handle.name
        original = MCP.consumers.CONFIG_PATH
        try:
            MCP.consumers.CONFIG_PATH = path
            document = MCP.TOOLS_BY_NAME["wanquota_settings"]["handler"]({})
        finally:
            MCP.consumers.CONFIG_PATH = original
            os.unlink(path)
        self.assertEqual(document["settings"]["smtp_host"], "mail.example.invalid")
        self.assertEqual(document["settings"]["smtp_password"], "(withheld)")
        self.assertNotIn("a-real-secret", json.dumps(document))


class WritableFieldTests(unittest.TestCase):
    """Which settings a remote caller can reach, named deliberately.

    Tool names are not the whole boundary. There is no tool called "enforce", but
    wanquota_set_settings reaches the guardrail engine through a field, and a claim
    that MCP "cannot change routing" is false because of it. These fields are listed
    so the reach is a decision on the record rather than a side effect of the
    allowlist, matching what the WRITERS set does for tools.
    """

    # Fields that let an agent start something which then acts on its own schedule.
    CONSEQUENTIAL = {
        "enforcement_enabled",        # the guardrail engine may change gateway routing
        "enforcement_dry_run",
        "enforcement_policy",
        "guardrail_thresholds",
        "emergency_reserve_gb",
        "device_enforcement_enabled", # the budget enforcer may block a device
        "device_enforcement_dry_run",
        "shaper_enabled",             # limits begin shaping traffic
        "shaper_dry_run",
        "shaper_upload_experimental",  # installs raw ipfw rules and flips a global sysctl
    }

    def writable(self):
        source = (Path(__file__).parents[1]
                  / "src/opnsense/scripts/OPNsense/WanQuota/configure.php").read_text()
        block = source[source.index("const WRITABLE = ["):source.index("];")]
        return set(re.findall(r"'([a-z0-9_]+)'", block))

    def test_the_consequential_fields_are_writable_and_known(self):
        """Deliberate: the owner asked for full control. Recorded, not hidden."""
        writable = self.writable()
        for field in self.CONSEQUENTIAL:
            self.assertIn(field, writable, field)

    def test_no_unlisted_enforcement_field_becomes_writable(self):
        """A new enforcement-shaped field must be added to the list above knowingly."""
        suspicious = {name for name in self.writable()
                      if "enforce" in name or "shaper" in name or "guardrail" in name}
        self.assertEqual(suspicious - self.CONSEQUENTIAL, set(),
                         "an engine-starting field was made writable without being listed")

    def test_the_override_verb_is_not_reachable_as_a_field(self):
        """Performing an override stays a separate endpoint, not a setting."""
        writable = self.writable()
        self.assertFalse(any("override" in name for name in writable))
