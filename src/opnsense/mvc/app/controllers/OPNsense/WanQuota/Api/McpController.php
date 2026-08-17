<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\WanQuota\McpGateway;

/**
 * Model Context Protocol endpoint.
 *
 * A thin shim over the mcp.py configd action, matching ReportController: the
 * protocol itself lives in Python so it stays under unit test, and this class
 * only moves bytes. OPNsense API key authentication is inherited from
 * ApiControllerBase, so agents authenticate exactly as they do for any other
 * endpoint.
 *
 * The transport decisions live in McpGateway, which has no framework dependency
 * and is covered by tests; CI can only lint this file.
 *
 * The client address is forwarded so mcp.py can refuse anything that is not on
 * the LAN. That check is defence in depth, not the primary control: this
 * endpoint is served by the OPNsense web GUI, so the interfaces the GUI listens
 * on and the firewall rules in front of it decide what can reach it at all.
 *
 * Returns a string, not an array. Returning an array would round-trip the
 * payload through json_decode/json_encode, and PHP cannot tell an empty JSON
 * object from an empty list, which silently corrupts the tool schemas.
 */
class McpController extends ApiControllerBase
{
    public function indexAction()
    {
        $this->response->setContentType('application/json', 'UTF-8');

        if (!$this->request->isPost()) {
            // A GET is a client asking to open a server-initiated stream, which
            // this server does not offer.
            $this->response->setStatusCode(405, 'Method Not Allowed');
            $this->response->setHeader('Allow', 'POST');
            return McpGateway::fault(-32600, 'POST required');
        }

        $body = (string)$this->request->getRawBody();
        if ($body === '') {
            return McpGateway::fault(-32700, 'Empty request body');
        }

        $client = $this->request->getClientAddress();
        if (!McpGateway::isValidClient($client)) {
            return McpGateway::fault(-32000, 'WAN quota MCP is reachable from the LAN only');
        }

        $raw = (new Backend())->configdRun(
            'wanquota mcp ' . escapeshellarg(McpGateway::encodeBody($body))
            . ' ' . escapeshellarg((string)$client)
        );

        $result = McpGateway::interpret((string)$raw);
        if ($result['status'] !== 200) {
            $this->response->setStatusCode($result['status'], 'Accepted');
        }
        return $result['body'];
    }
}
