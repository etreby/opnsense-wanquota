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
    /**
     * Returns the backend's JSON verbatim as a string rather than a decoded
     * array. Returning an array would round-trip the payload through
     * json_decode(..., true) and json_encode(), and PHP cannot tell an empty
     * JSON object from an empty list: {} decodes to [] and re-encodes as [].
     * That silently rewrote every "properties": {} in the tool schemas into
     * "properties": [], which MCP clients reject as a malformed tools/list.
     * The base controller passes a returned string through untouched.
     */
    public function indexAction()
    {
        $this->response->setContentType('application/json', 'UTF-8');
        if (!$this->request->isPost()) {
            // MCP over HTTP defines this endpoint as POST for client messages.
            // A GET is the client asking to open a server-initiated stream, which
            // this server does not offer; 405 tells it so rather than looking like
            // a malformed request.
            $this->response->setStatusCode(405, 'Method Not Allowed');
            $this->response->setHeader('Allow', 'POST');
            return $this->fault(-32600, 'POST required');
        }

        $body = (string)$this->request->getRawBody();
        if ($body === '') {
            return $this->fault(-32700, 'Empty request body');
        }

        $client = (string)$this->request->getClientAddress();
        if (filter_var($client, FILTER_VALIDATE_IP) === false) {
            // Unknown origin is treated as untrusted rather than waved through.
            return $this->fault(-32000, 'WAN quota MCP is reachable from the LAN only');
        }

        $encoded = base64_encode($body);
        $raw = (new Backend())->configdRun(
            'wanquota mcp ' . escapeshellarg($encoded) . ' ' . escapeshellarg($client)
        );
        $result = json_decode($raw, true);
        if (!is_array($result)) {
            return $this->fault(-32603, 'WAN quota MCP backend unavailable');
        }
        if (!empty($result['_notification'])) {
            // A JSON-RPC notification has no response body.
            $this->response->setStatusCode(202, 'Accepted');
            return '';
        }
        return $raw;
    }

    private function fault(int $code, string $message): string
    {
        return (string)json_encode([
            'jsonrpc' => '2.0',
            'id' => null,
            'error' => ['code' => $code, 'message' => $message],
        ]);
    }
}
