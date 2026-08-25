<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\WanQuota\WanQuota;

/**
 * Renewal-aware WAN balance, for the Intelligence tab.
 *
 * Outside api/wanquota/report/* for the same reason as the other write endpoints:
 * that prefix is the read-only privilege, and this endpoint changes how traffic is
 * routed.
 *
 * The arithmetic is balance.py's and stays there. This reads the plan and turns
 * three switches, which is deliberately all it does — a controller that recomputed
 * the plan itself would give the interface and the five-minute collector two
 * different answers to the same question.
 */
class BalanceController extends ApiControllerBase
{
    /** The current plan, the gateway inventory behind it, and the switches. */
    public function getAction(): array
    {
        $backend = new Backend();
        /*
         * `balanceplan` recomputes and, when the configuration permits, applies. That
         * is right for the collector and wrong for a page load, so the interface reads
         * the stored plan. It is refreshed every five minutes; Recalculate is the
         * button for wanting it sooner.
         */
        $plan = json_decode($backend->configdRun('wanquota balancestate'), true);
        $plan = is_array($plan) ? $plan : ['status' => 'failed', 'providers' => []];

        $model = new WanQuota();
        $plan['enabled'] = (string)$model->general->balance_enabled === '1';
        $plan['dry_run'] = (string)$model->general->balance_dry_run === '1';
        $plan['configured_group'] = (string)$model->general->balance_group;
        $plan['max_weight'] = (int)(string)$model->general->balance_max_weight;

        /* Group names so the interface can offer a choice rather than a text field. */
        $inventory = json_decode($backend->configdRun('wanquota balanceinventory'), true);
        $plan['groups'] = array_map(
            fn($group) => ['name' => $group['name'], 'members' => $group['members'],
                           'poolopts' => $group['poolopts'] ?? ''],
            $inventory['groups'] ?? []
        );
        return $plan;
    }

    /**
     * Turn the switches, then recompute.
     *
     * Recomputing here is what makes the interface honest: switching off dry-run and
     * being shown the previous plan would show weights computed under different
     * settings, and the user would read them as what is now live.
     */
    public function setAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $model = new WanQuota();
        foreach (['enabled' => 'balance_enabled', 'dry_run' => 'balance_dry_run'] as $key => $field) {
            /* Explicit null default rather than has(): a JSON body does not populate
               $_REQUEST, so has() would report every switch as absent. */
            $value = $this->request->getPost($key, null, null);
            if ($value !== null) {
                $model->general->$field = $value ? '1' : '0';
            }
        }
        $group = $this->request->getPost('group', null, null);
        if ($group !== null) {
            $model->general->balance_group = preg_replace('/[^a-zA-Z0-9_\-]/', '', (string)$group);
        }
        $maxWeight = $this->request->getPost('max_weight', null, null);
        if ($maxWeight !== null && $maxWeight !== '') {
            $model->general->balance_max_weight = (string)max(2, min(10, (int)$maxWeight));
        }
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save('Update WAN quota renewal-aware balance settings');

        $plan = json_decode((new Backend())->configdRun('wanquota balanceplan'), true);
        return ['status' => 'ok', 'plan' => is_array($plan) ? $plan : null];
    }

    /**
     * Apply the balance now, whatever dry-run says.
     *
     * A deliberate override, not a leak: the button is labelled as one, it is only
     * reachable by an account holding the full privilege, and Revert beside it puts
     * every weight back. Someone who has read the plan and wants it should not have
     * to disable dry-run — which would also hand the five-minute collector permission
     * they had not decided on yet — merely to try it once.
     */
    public function applyAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $result = json_decode((new Backend())->configdRun('wanquota balanceapply'), true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'error' => 'The balance could not be applied'];
        }
        return $result;
    }

    /** Put every weight the balancer changed back where it found it. */
    public function revertAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $result = json_decode((new Backend())->configdRun('wanquota balancerevert'), true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'error' => 'The gateway weights could not be restored'];
        }
        return $result;
    }
}
