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
    def test_initialize_echoes_client_protocol_version(self):
        response = MCP.handle(request("initialize", {"protocolVersion": "2025-06-18"}))
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(response["result"]["serverInfo"]["name"], "wanquota")

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
        self.assertEqual(len(tools), 7)
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_tool_surface_is_read_only(self):
        names = {tool["name"] for tool in MCP.tool_descriptors()}
        self.assertNotIn("wanquota_override", names)
        self.assertFalse(any("override" in name or "enforce" in name for name in names))

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
        self.assertEqual(len(response["result"]["tools"]), 7)

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
        self.assertEqual(len(response["result"]["tools"]), 7)

    def test_once_rejects_invalid_base64(self):
        response = MCP.serve_once("not base64 !!!")
        self.assertEqual(response["error"]["code"], MCP.PARSE_ERROR)

    def test_once_tolerates_wrapped_base64(self):
        # FreeBSD's b64encode wraps at 76 columns; the embedded newline must not
        # be read as a malformed request.
        raw = base64.b64encode(json.dumps(request("tools/list")).encode()).decode()
        wrapped = "\n".join([raw[:40], raw[40:]]) + "\n"
        response = MCP.serve_once(wrapped)
        self.assertEqual(len(response["result"]["tools"]), 7)


if __name__ == "__main__":
    unittest.main()
