<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;

class ReportController extends ApiControllerBase
{
    private function runReport(string $mode): array
    {
        $raw = (new Backend())->configdRun('wanquota ' . $mode);
        $result = json_decode($raw, true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'providers' => [], 'error' => 'WAN quota report unavailable'];
        }
        return $result;
    }

    public function summaryAction(): array
    {
        return $this->runReport('summary');
    }

    public function dailyAction(): array
    {
        return $this->runReport('daily');
    }

    public function monthlyAction(): array
    {
        return $this->runReport('monthly');
    }

    public function healthAction(): array
    {
        return $this->runReport('health');
    }

    public function consumersTodayAction(): array
    {
        return $this->runReport('consumers today');
    }

    public function consumersWeekAction(): array
    {
        return $this->runReport('consumers week');
    }

    public function consumersThirtyAction(): array
    {
        return $this->runReport('consumers thirty');
    }

    public function consumersMonthAction(): array
    {
        return $this->runReport('consumers month');
    }

    public function intelligenceTodayAction(): array
    {
        return $this->runReport('intelligence today');
    }

    public function intelligenceWeekAction(): array
    {
        return $this->runReport('intelligence week');
    }

    public function intelligenceThirtyAction(): array
    {
        return $this->runReport('intelligence thirty');
    }

    public function intelligenceMonthAction(): array
    {
        return $this->runReport('intelligence month');
    }

    public function sessionsAction(): array
    {
        return $this->runReport('sessions 500');
    }

    /**
     * Explain one domain. Read-only, so it sits with the reporting endpoints and is
     * reachable by the read-only privilege.
     */
    public function explainAction(): array
    {
        $domain = preg_replace('/[^a-zA-Z0-9._-]/', '', (string)$this->request->get('domain'));
        if ($domain === '') {
            return ['status' => 'failed', 'error' => 'A domain is required'];
        }
        return $this->runReport('explain ' . escapeshellarg($domain) . ' thirty');
    }

    public function metricsAction(): array
    {
        $raw = (new Backend())->configdRun('wanquota metrics');
        return ['status' => 'ok', 'content_type' => 'text/plain; version=0.0.4', 'metrics' => $raw];
    }

}
