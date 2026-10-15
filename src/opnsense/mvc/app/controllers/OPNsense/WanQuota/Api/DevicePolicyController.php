<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\WanQuota\WanQuota;

/**
 * Per-device data quotas and internet blocks, for the Limits tab's Quota & access
 * sub-tab.
 *
 * Deliberately not under api/wanquota/report, and for a sharper reason than the
 * other write endpoints: the read-only ACL privilege matches api/wanquota/report/*
 * and is the credential an AI agent should be given. An endpoint that can take a
 * device off the internet must not be reachable through a privilege whose name
 * promises it only reads.
 *
 * The two features share this controller because they share a table row in the
 * interface — a device's quota and its access are one decision made in one place —
 * but they are stored, enforced and reverted separately. Nothing here mixes them.
 */
class DevicePolicyController extends ApiControllerBase
{
    /** Devices, their quota, what they have used this month, and their access state. */
    public function getAction(): array
    {
        $backend = new Backend();
        $known = json_decode($backend->configdRun('wanquota shaperdevices'), true);
        /*
         * The month, because a device budget is a calendar-month allowance rather
         * than a provider cycle: a device's bytes are split across both links by the
         * load balancer, so there is no single cycle its traffic belongs to.
         */
        $usage = json_decode($backend->configdRun('wanquota consumers month'), true);
        /* State, not a fresh run: rendering a page must not apply a firewall table. */
        $budgetPlan = json_decode($backend->configdRun('wanquota devicestate'), true);
        $blockPlan = json_decode($backend->configdRun('wanquota blockstate'), true);

        $model = new WanQuota();
        $policies = json_decode((string)$model->general->device_policies_json, true);
        $policies = is_array($policies) ? $policies : [];
        $blocks = json_decode((string)$model->general->device_blocks_json, true);
        $blocks = is_array($blocks) ? $blocks : [];

        /* Index every stored entry by every identifier it may carry, lowercased. */
        $quotaBy = [];
        foreach ($policies as $policy) {
            foreach (['address', 'mac', 'hostname'] as $field) {
                if (!empty($policy[$field])) {
                    $quotaBy[strtolower((string)$policy[$field])] = $policy;
                }
            }
        }
        $blockBy = [];
        foreach ($blocks as $block) {
            if (!empty($block['device'])) {
                $blockBy[strtolower((string)$block['device'])] = $block;
            }
        }
        $usedBy = [];
        foreach (($usage['hosts'] ?? []) as $host) {
            if (!empty($host['ip'])) {
                $usedBy[strtolower((string)$host['ip'])] = (float)($host['total'] ?? 0);
            }
        }
        $overBudget = [];
        foreach (($budgetPlan['members'] ?? []) as $member) {
            $overBudget[strtolower((string)$member['device'])] = $member;
        }
        $blockedNow = [];
        foreach (($blockPlan['members'] ?? []) as $member) {
            $blockedNow[strtolower((string)$member['device'])] = $member;
        }
        $blockRefused = [];
        foreach (($blockPlan['skipped'] ?? []) as $entry) {
            $blockRefused[strtolower((string)$entry['device'])] = $entry['reason'];
        }

        /*
         * A MAC is the better key because it survives a DHCP move — but only when it
         * identifies one device. Two host addresses can sit behind one MAC as the
         * firewall sees it: a workstation with a wired and a wireless address reached
         * through the same intermediate device presents both on that device's MAC.
         * Keying both rows on it gave two rows the same key, and the endpoint rejected
         * the whole save as a duplicate — so no quota and no block could be saved at
         * all, for any device on the network. Seen on a live firewall.
         */
        $macCount = [];
        foreach (($known['devices'] ?? []) as $device) {
            $mac = strtolower((string)$device['mac']);
            if ($mac !== '') {
                $macCount[$mac] = ($macCount[$mac] ?? 0) + 1;
            }
        }

        $rows = [];
        $matchedBlocks = [];
        foreach (($known['devices'] ?? []) as $device) {
            $identifiers = [$device['address'], $device['mac'], $device['hostname'], $device['name']];
            $quota = null;
            $block = null;
            $matchedOn = '';
            foreach ($identifiers as $candidate) {
                $key = strtolower((string)$candidate);
                if ($key === '') {
                    continue;
                }
                if ($quota === null && isset($quotaBy[$key])) {
                    $quota = $quotaBy[$key];
                }
                if ($block === null && isset($blockBy[$key])) {
                    $block = $blockBy[$key];
                    $matchedOn = (string)$candidate;
                }
            }
            if ($block !== null && !empty($block['device'])) {
                $matchedBlocks[strtolower((string)$block['device'])] = true;
            }
            $address = strtolower((string)$device['address']);
            $mac = strtolower((string)$device['mac']);
            $sharedMac = $mac !== '' && ($macCount[$mac] ?? 0) > 1;
            $uniqueKey = ($mac !== '' && !$sharedMac) ? $mac : (string)$device['address'];
            $used = $usedBy[$address] ?? 0.0;
            $budgetGb = (float)($quota['budget_gb'] ?? 0);
            $rows[] = [
                'address' => $device['address'],
                'name' => $device['name'],
                'mac' => $device['mac'],
                'hostname' => $device['hostname'],
                'name_source' => $device['name_source'],
                /*
                 * The MAC is preferred, but only when it is unambiguous; a shared MAC
                 * cannot tell two devices apart, so those rows key on their address
                 * and the interface says the policy will not survive a DHCP move.
                 */
                'key' => $block['device'] ?? $uniqueKey,
                'key_is_mac' => $uniqueKey === strtolower((string)$device['mac'])
                    && $uniqueKey !== '',
                'shared_mac' => $sharedMac,
                'budget_gb' => $budgetGb > 0 ? $budgetGb : '',
                'excluded' => !empty($quota['exclude']),
                'used' => $used,
                'percent' => $budgetGb > 0 ? min(999, $used / ($budgetGb * 1e9) * 100) : null,
                'over_budget' => isset($overBudget[$address]),
                'blocked' => $block !== null,
                'blocked_now' => isset($blockedNow[$address]),
                'until' => (int)($block['until'] ?? 0),
                'reason' => (string)($block['reason'] ?? ''),
                'block_refused' => $blockRefused[strtolower($matchedOn)]
                    ?? ($blockRefused[$address] ?? null),
            ];
        }

        /* Include any manual blocks that did not match a known LAN device inventory row */
        foreach ($blocks as $block) {
            $bKey = strtolower(trim((string)($block['device'] ?? '')));
            if ($bKey === '' || isset($matchedBlocks[$bKey])) {
                continue;
            }
            $target = (string)$block['device'];
            $rows[] = [
                'address' => $target,
                'name' => $target,
                'mac' => '',
                'hostname' => '',
                'name_source' => 'manual',
                'key' => $target,
                'key_is_mac' => false,
                'shared_mac' => false,
                'budget_gb' => '',
                'excluded' => false,
                'used' => 0.0,
                'percent' => null,
                'over_budget' => false,
                'blocked' => true,
                'blocked_now' => isset($blockedNow[strtolower($target)]),
                'until' => (int)($block['until'] ?? 0),
                'reason' => (string)($block['reason'] ?? ''),
                'block_refused' => $blockRefused[$bKey] ?? null,
            ];
        }

        return [
            'status' => 'ok',
            'enforcement_enabled' => (string)$model->general->device_enforcement_enabled === '1',
            'enforcement_dry_run' => (string)$model->general->device_enforcement_dry_run === '1',
            'budget_table' => $budgetPlan['table'] ?? 'wanquota_over_budget',
            'block_table' => $blockPlan['table'] ?? 'wanquota_blocked',
            'budget_note' => $budgetPlan['note'] ?? null,
            'block_note' => $blockPlan['note'] ?? null,
            'period' => 'month',
            'devices' => $rows,
        ];
    }

    /**
     * Save quotas and blocks together, then enforce.
     *
     * One endpoint because the interface offers one Save for one table of rows.
     * Saving them separately would let a page that set a quota and a block succeed
     * at one and fail at the other, leaving the interface disagreeing with the
     * configuration about what the user just did.
     */
    public function setAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $model = new WanQuota();
        $errors = [];

        /*
         * Quotas are merged into device_policies_json rather than replacing it. The
         * field also carries `exclude`, and the Intelligence tab writes group policy
         * into the same store; replacing it wholesale from a quota form would discard
         * an exclusion the user set elsewhere, which is the one flag that protects a
         * device from being blocked.
         */
        $existing = json_decode((string)$model->general->device_policies_json, true);
        $existing = is_array($existing) ? $existing : [];
        $byKey = [];
        foreach ($existing as $index => $policy) {
            foreach (['address', 'mac', 'hostname'] as $field) {
                if (!empty($policy[$field])) {
                    $byKey[strtolower((string)$policy[$field])] = $index;
                }
            }
        }
        $seen = [];
        foreach ((array)$this->request->getPost('quotas') as $item) {
            $key = trim((string)($item['device'] ?? ''));
            if ($key === '') {
                continue;
            }
            $lower = strtolower($key);
            $raw = trim((string)($item['budget_gb'] ?? ''));
            /*
             * A repeated key is only a conflict when the two entries disagree. The page
             * posts every row, so an identifier shared by two rows arrives twice with
             * nothing set on either — refusing the request for that rejected the whole
             * save and made the tab unusable rather than reporting a problem with one
             * row. Identical values collapse; only a genuine disagreement is an error,
             * and it names both values so it can be acted on.
             */
            if (isset($seen[$lower])) {
                if ($seen[$lower] !== $raw) {
                    $errors[] = sprintf(
                        '%s is listed twice with different quotas (%s and %s); it is one '
                        . 'device to this firewall, so it can carry only one',
                        $key, $seen[$lower] === '' ? 'none' : $seen[$lower],
                        $raw === '' ? 'none' : $raw);
                }
                continue;
            }
            $seen[$lower] = $raw;
            $index = $byKey[$lower] ?? null;
            if ($raw === '' || (float)$raw <= 0) {
                /* Clearing a quota removes the budget but keeps the entry when it
                   carries anything else worth keeping, such as an exclusion. */
                if ($index !== null) {
                    unset($existing[$index]['budget_gb']);
                    if (count(array_diff_key($existing[$index], ['address' => 1, 'mac' => 1, 'hostname' => 1])) === 0) {
                        unset($existing[$index]);
                    }
                }
                continue;
            }
            if (!is_numeric($raw) || (float)$raw <= 0) {
                $errors[] = sprintf('%s: the quota must be a positive number of GB', $key);
                continue;
            }
            if ($index !== null) {
                $existing[$index]['budget_gb'] = (float)$raw;
            } else {
                /* A MAC is stored as a MAC so the quota survives a DHCP change. */
                $field = preg_match('/^([0-9a-f]{2}:){5}[0-9a-f]{2}$/i', $key) ? 'mac' : 'address';
                $existing[] = [$field => $key, 'budget_gb' => (float)$raw];
            }
        }

        /* Blocks replace wholesale: the form is the complete list of who is blocked. */
        $blocks = [];
        $blockSeen = [];
        foreach ((array)$this->request->getPost('blocks') as $item) {
            $key = trim((string)($item['device'] ?? ''));
            if ($key === '') {
                continue;
            }
            $lower = strtolower($key);
            $until = (int)($item['until'] ?? 0);
            /* Same reasoning as the quotas: blocking one device twice is a repeat, not
               a conflict, unless the two deadlines disagree about when it ends. */
            if (isset($blockSeen[$lower])) {
                if ($blockSeen[$lower] !== $until) {
                    $errors[] = sprintf(
                        '%s is blocked twice with different deadlines; it is one device '
                        . 'to this firewall, so it can carry only one', $key);
                }
                continue;
            }
            $blockSeen[$lower] = $until;
            if ($until < 0) {
                $errors[] = sprintf('%s: the block deadline is not a valid time', $key);
                continue;
            }
            /*
             * A deadline already in the past is refused rather than accepted and
             * expired on the next pass. Accepting it would show the device as blocked
             * until the collector ran, which is up to five minutes of the interface
             * saying something untrue.
             */
            if ($until > 0 && $until <= time()) {
                $errors[] = sprintf('%s: the block deadline is already in the past', $key);
                continue;
            }
            $blocks[] = [
                'device' => $key,
                'until' => $until,
                'reason' => substr(preg_replace('/[^\PC\s]/u', '', (string)($item['reason'] ?? '')), 0, 200),
                'created' => time(),
            ];
        }

        if ($errors) {
            return ['status' => 'failed', 'errors' => $errors];
        }

        $model->general->device_policies_json = json_encode(array_values($existing));
        $model->general->device_blocks_json = json_encode($blocks);
        foreach (['enforcement_enabled' => 'device_enforcement_enabled',
                  'enforcement_dry_run' => 'device_enforcement_dry_run'] as $key => $field) {
            /* getPost with an explicit null default, not has(): a JSON body does not
               populate $_REQUEST, so has() would report every switch as absent. */
            $value = $this->request->getPost($key, null, null);
            if ($value !== null) {
                $model->general->$field = $value ? '1' : '0';
            }
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
        \OPNsense\Core\Config::getInstance()->save('Update WAN quota device quotas and blocks');

        $backend = new Backend();
        /* Blocks first: an explicit block should not wait behind a budget
           recomputation that reads several databases and can fail. */
        $blockResult = json_decode($backend->configdRun('wanquota blockrun'), true);
        $budgetResult = json_decode($backend->configdRun('wanquota deviceenforce month'), true);
        return [
            'status' => 'ok',
            'quotas' => count(array_filter($existing, fn($item) => !empty($item['budget_gb']))),
            'blocks' => count($blocks),
            'block_result' => $blockResult,
            'budget_result' => $budgetResult,
        ];
    }

    /**
     * Release every block at once.
     *
     * The panic button. Empties the field and flushes the table, so a household
     * locked out by a mistake is one click from working again rather than editing
     * rows.
     */
    public function unblockAllAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $model = new WanQuota();
        $model->general->device_blocks_json = '[]';
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save('Release every WAN quota device block');
        $flushed = json_decode((new Backend())->configdRun('wanquota blockflush'), true);
        return ['status' => 'ok', 'flushed' => $flushed];
    }

    public function unblock_allAction(): array
    {
        return $this->unblockAllAction();
    }

    /**
     * Block a single device with duration and optional reason.
     */
    public function blockAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $device = trim((string)$this->request->getPost('device'));
        if ($device === '') {
            return ['status' => 'failed', 'error' => 'No device specified'];
        }
        $rawDuration = trim((string)$this->request->getPost('duration', 0));
        $reason = substr(preg_replace('/[^\PC\s]/u', '', (string)$this->request->getPost('reason', '')), 0, 200);

        $until = 0;
        if (is_numeric($rawDuration)) {
            $num = (float)$rawDuration;
            if ($num > 0) {
                // If small number, interpret as hours, else as unix timestamp
                $until = $num < 100000000 ? time() + (int)($num * 3600) : (int)$num;
            }
        } elseif (preg_match('/^(\d+)\s*(h|hr|hours?|d|days?|m|min|minutes?)$/i', $rawDuration, $matches)) {
            $val = (int)$matches[1];
            $unit = strtolower($matches[2][0]);
            if ($unit === 'm') {
                $until = time() + ($val * 60);
            } elseif ($unit === 'h') {
                $until = time() + ($val * 3600);
            } elseif ($unit === 'd') {
                $until = time() + ($val * 86400);
            }
        }

        if ($until > 0 && $until <= time()) {
            return ['status' => 'failed', 'error' => 'The block deadline must be in the future'];
        }

        $model = new WanQuota();
        $blocks = json_decode((string)$model->general->device_blocks_json, true);
        $blocks = is_array($blocks) ? $blocks : [];

        $lower = strtolower($device);
        $found = false;
        foreach ($blocks as &$item) {
            if (strtolower(trim((string)($item['device'] ?? ''))) === $lower) {
                $item['until'] = $until;
                $item['reason'] = $reason;
                $item['created'] = time();
                $found = true;
                break;
            }
        }
        unset($item);

        if (!$found) {
            $blocks[] = [
                'device' => $device,
                'until' => $until,
                'reason' => $reason,
                'created' => time(),
            ];
        }

        $model->general->device_blocks_json = json_encode(array_values($blocks));
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save(sprintf('Block device %s from the internet (os-wanquota)', $device));

        $backend = new Backend();
        $blockResult = json_decode($backend->configdRun('wanquota blockrun'), true);

        return [
            'status' => 'ok',
            'device' => $device,
            'until' => $until,
            'reason' => $reason,
            'block_result' => $blockResult,
        ];
    }

    /**
     * Unblock a single device.
     */
    public function unblockAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $device = trim((string)$this->request->getPost('device'));
        if ($device === '') {
            return ['status' => 'failed', 'error' => 'No device specified'];
        }
        $lower = strtolower($device);

        $model = new WanQuota();
        $blocks = json_decode((string)$model->general->device_blocks_json, true);
        $blocks = is_array($blocks) ? $blocks : [];

        $filtered = [];
        $removed = false;
        foreach ($blocks as $item) {
            if (strtolower(trim((string)($item['device'] ?? ''))) === $lower) {
                $removed = true;
                continue;
            }
            $filtered[] = $item;
        }

        $model->general->device_blocks_json = json_encode(array_values($filtered));
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save(sprintf('Unblock device %s (os-wanquota)', $device));

        $backend = new Backend();
        $blockResult = json_decode($backend->configdRun('wanquota blockrun'), true);

        return [
            'status' => 'ok',
            'device' => $device,
            'removed' => $removed,
            'block_result' => $blockResult,
        ];
    }
}
