<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

/**
 * Model Context Protocol endpoint.
 *
 * A thin shim over the mcp.py configd action, matching ReportController: the
 * protocol itself lives in Python so it stays under unit test, and this class
 * only moves bytes. OPNsense API key authentication is inherited from
 * ApiControllerBase, so agents authenticate exactly as they do for any other
 * endpoint.
 *
 * The request body is base64 encoded before it reaches configd because configd
 * splits parameters on whitespace; JSON-RPC payloads contain plenty of it.
 *
 * The client address is forwarded so mcp.py can refuse anything that is not on
 * the LAN. That check is defence in depth, not the primary control: this
 * endpoint is served by the OPNsense web GUI, so the interfaces the GUI listens
 * on and the firewall rules in front of it decide what can reach it at all.
 */
class McpController extends ApiControllerBase
{
    public function indexAction(): array
    {
        if (!$this->request->isPost()) {
            return [
                'jsonrpc' => '2.0',
                'id' => null,
                'error' => ['code' => -32600, 'message' => 'POST required'],
            ];
        }

        $body = (string)$this->request->getRawBody();
        if ($body === '') {
            return [
                'jsonrpc' => '2.0',
                'id' => null,
                'error' => ['code' => -32700, 'message' => 'Empty request body'],
            ];
        }

        $client = (string)$this->request->getClientAddress();
        if (filter_var($client, FILTER_VALIDATE_IP) === false) {
            // Unknown origin is treated as untrusted rather than waved through.
            return [
                'jsonrpc' => '2.0',
                'id' => null,
                'error' => ['code' => -32000, 'message' => 'WAN quota MCP is reachable from the LAN only'],
            ];
        }

        $encoded = base64_encode($body);
        $raw = (new Backend())->configdRun(
            'wanquota mcp ' . escapeshellarg($encoded) . ' ' . escapeshellarg($client)
        );
        $result = json_decode($raw, true);
        if (!is_array($result)) {
            return [
                'jsonrpc' => '2.0',
                'id' => null,
                'error' => ['code' => -32603, 'message' => 'WAN quota MCP backend unavailable'],
            ];
        }
        return $result;
    }
}
