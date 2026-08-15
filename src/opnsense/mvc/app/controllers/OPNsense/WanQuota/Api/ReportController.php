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
}
