<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

/**
 * Temporary guardrail overrides.
 *
 * This is the only endpoint in the plugin that changes how traffic is routed,
 * so it lives apart from the read-only reporting endpoints. ACL patterns match
 * on the URL, so an override action hosted inside ReportController could not be
 * excluded from a read-only privilege covering api/wanquota/report/*. Keeping it
 * on its own path is what makes a genuinely read-only credential possible — the
 * one an AI agent should be given.
 */
class OverrideController extends ApiControllerBase
{
    public function indexAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $provider = preg_replace('/[^a-zA-Z0-9 _.-]/', '', (string)$this->request->getPost('provider'));
        $mode = (string)$this->request->getPost('mode');
        $hours = max(1, min(168, (int)$this->request->getPost('hours')));
        if ($provider === '' || !in_array($mode, ['observe', 'deprioritize', 'failover', 'cutoff'], true)) {
            return ['status' => 'failed', 'error' => 'Invalid override'];
        }
        $raw = (new Backend())->configdRun(sprintf(
            'wanquota override %s %s %d api',
            escapeshellarg($provider),
            escapeshellarg($mode),
            $hours
        ));
        $result = json_decode($raw, true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'error' => 'WAN quota override unavailable'];
        }
        return $result;
    }
}
