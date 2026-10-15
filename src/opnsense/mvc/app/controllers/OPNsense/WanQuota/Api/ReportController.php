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

    /**
     * The renewal-aware balance, read only.
     *
     * A mirror of what BalanceController::get reports, and it exists so a dashboard
     * widget and a read-only credential can see which link is carrying traffic
     * without being given the endpoint that can change it. `balancestate` prints the
     * stored plan and computes nothing, so this cannot apply anything as a side
     * effect of being looked at.
     */
    public function balanceAction(): array
    {
        return $this->runReport('balancestate');
    }

    /**
     * Which devices are currently blocked or over their quota, read only.
     *
     * Both come from stored plans rather than a fresh evaluation, for the same
     * reason: rendering a widget must not apply a firewall table.
     */
    public function accessAction(): array
    {
        $backend = new Backend();
        $blocks = json_decode($backend->configdRun('wanquota blockstate'), true);
        $budgets = json_decode($backend->configdRun('wanquota devicestate'), true);
        return [
            'status' => 'ok',
            'blocked' => is_array($blocks) ? ($blocks['members'] ?? []) : [],
            'blocked_refused' => is_array($blocks) ? ($blocks['skipped'] ?? []) : [],
            'over_budget' => is_array($budgets) ? ($budgets['members'] ?? []) : [],
            'budget_state' => is_array($budgets) ? ($budgets['status'] ?? 'unknown') : 'unknown',
            'budget_dry_run' => is_array($budgets) ? ($budgets['dry_run'] ?? null) : null,
        ];
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

    public function consumersDateAction(): array
    {
        $rawDate = (string)($this->request->getPost('date') ?: $this->request->getQuery('date') ?: ($_REQUEST['date'] ?? ''));
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $rawDate)) {
            return ['status' => 'failed', 'error' => 'A valid date (YYYY-MM-DD) is required'];
        }
        return $this->runReport('consumers date ' . $rawDate);
    }

    public function consumers_dateAction(): array
    {
        return $this->consumersDateAction();
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
        $rawDomain = (string)($this->request->getPost('domain') ?: $this->request->getQuery('domain') ?: ($_REQUEST['domain'] ?? ''));
        $domain = preg_replace('/[^a-zA-Z0-9._-]/', '', $rawDomain);
        if ($domain === '') {
            return ['status' => 'failed', 'error' => 'A domain is required'];
        }
        return $this->runReport('explain ' . escapeshellarg($domain) . ' thirty');
    }

    /**
     * Live throughput per WAN.
     *
     * Read-only and cheap, but it samples the interface counters over a second, so it
     * is a poll rather than part of the summary: a report that blocks for a second
     * every time it loads would be worse than a separate call the interface makes only
     * while someone is watching.
     */
    public function throughputAction(): array
    {
        return $this->runReport('throughput 1');
    }

    public function metricsAction(): array
    {
        $raw = (new Backend())->configdRun('wanquota metrics');
        return ['status' => 'ok', 'content_type' => 'text/plain; version=0.0.4', 'metrics' => $raw];
    }

}
