import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
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

    def test_every_tool_declares_itself_read_only(self):
        # Without the hint a cautious client prompts before each call, which
        # wastes the guarantee the whole surface was designed around.
        for tool in MCP.handle(request("tools/list"))["result"]["tools"]:
            self.assertTrue(tool["annotations"]["readOnlyHint"], tool["name"])
            self.assertFalse(tool["annotations"]["destructiveHint"], tool["name"])
            self.assertTrue(tool["annotations"]["title"], tool["name"])

    def test_no_argument_schemas_survive_as_objects(self):
        # These serialise to {} and a transport that turns them into [] breaks
        # every client; keep the shape asserted at the source.
        for tool in MCP.handle(request("tools/list"))["result"]["tools"]:
            self.assertIsInstance(tool["inputSchema"]["properties"], dict, tool["name"])

    def test_tool_surface_is_read_only(self):
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

    def test_drill_tools_are_still_read_only(self):
        for tool in ("wanquota_device", "wanquota_site"):
            self.assertIn(tool, MCP.TOOLS_BY_NAME)
        names = {t["name"] for t in MCP.tool_descriptors()}
        self.assertFalse(any("override" in n or "enforce" in n or "set" in n for n in names))


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
