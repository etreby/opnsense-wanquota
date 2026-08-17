<?php

namespace OPNsense\WanQuota\Api;

use OPNsense\Base\ApiControllerBase;
use OPNsense\Core\Backend;
use OPNsense\WanQuota\WanQuota;

/**
 * Per-service bandwidth limits, for the Limits tab.
 *
 * Deliberately not under api/wanquota/report, so the read-only privilege that an
 * AI agent's key should hold does not reach it: this endpoint changes how traffic
 * is shaped.
 *
 * The catalog and the observed address counts come from shaper.py, which is the
 * single source of truth for what can be limited and how well it can be matched.
 * The interface never invents a service.
 */
class LimitsController extends ApiControllerBase
{
    /**
     * Apply the shared enable and dry-run switches, if the caller sent them.
     *
     * Both switches govern service and device limits together, so a request that
     * omits them must leave them alone rather than reading absent as off. Treating
     * absence as off is how saving a device limit once disabled the service limits
     * too: the two sub-tabs each had their own switch writing the same field, and the
     * one that happened to be unticked won. The interface now has a single pair, and
     * this makes the endpoint safe for any other caller as well.
     */
    private function applyState(WanQuota $model): void
    {
        foreach (['enabled' => 'shaper_enabled', 'dry_run' => 'shaper_dry_run'] as $key => $field) {
            /*
             * getPost with an explicit null default rather than has(): a JSON request
             * body does not populate $_REQUEST, so has() would report every switch as
             * absent and none would ever be applied. This form reads the same whether
             * the caller sent JSON or a form, and distinguishes "sent as 0" from
             * "not sent".
             */
            $value = $this->request->getPost($key, null, null);
            if ($value !== null) {
                $model->general->$field = $value ? '1' : '0';
            }
        }
    }

    /** Devices the firewall can name, with any limit already set on them. */
    public function devicesAction(): array
    {
        $backend = new Backend();
        $plan = json_decode($backend->configdRun('wanquota shaperplan'), true);
        $known = json_decode($backend->configdRun('wanquota shaperdevices'), true);

        $model = new WanQuota();
        $configured = json_decode((string)$model->general->device_limits_json, true);
        $configured = is_array($configured) ? $configured : [];
        $selected = [];
        foreach ($configured as $item) {
            if (!empty($item['device'])) {
                $selected[strtolower((string)$item['device'])] = $item;
            }
        }
        $refused = [];
        foreach (($plan['device_rejected'] ?? []) as $entry) {
            $refused[strtolower((string)$entry['device'])] = $entry['reason'];
        }
        /*
         * Upload refusals are separate from device refusals: the device is limited,
         * only its upload half was declined. Keyed on the identifier the user typed
         * so the message lands on the row they edited.
         */
        $uploadRefused = [];
        foreach (($plan['upload_rejected'] ?? []) as $entry) {
            $uploadRefused[strtolower((string)$entry['device'])] = $entry['reason'];
        }

        $rows = [];
        foreach (($known['devices'] ?? []) as $device) {
            /*
             * A limit may be keyed on the address, the MAC or the DHCP hostname, so a
             * row is considered configured if any of its identifiers matches. MAC is
             * offered as the preferred key because it survives a DHCP change.
             */
            $choice = null;
            $matchedOn = '';
            foreach ([$device['address'], $device['mac'], $device['hostname'], $device['name']] as $candidate) {
                $key = strtolower((string)$candidate);
                if ($key !== '' && isset($selected[$key])) {
                    $choice = $selected[$key];
                    $matchedOn = (string)$candidate;
                    break;
                }
            }
            $rows[] = [
                'address' => $device['address'],
                'name' => $device['name'],
                'mac' => $device['mac'],
                'hostname' => $device['hostname'],
                'name_source' => $device['name_source'],
                'selected' => $choice !== null && ($choice['enabled'] ?? true),
                'key' => $choice['device'] ?? ($device['mac'] ?: $device['address']),
                'matched_on' => $matchedOn,
                'mbit' => $choice['mbit'] ?? '',
                'upload_mbit' => $choice['upload_mbit'] ?? '',
                'refused' => $refused[strtolower((string)$device['address'])] ?? null,
                'upload_refused' => $uploadRefused[strtolower((string)$matchedOn)]
                    ?? ($uploadRefused[strtolower((string)$device['address'])] ?? null),
            ];
        }
        $interception = $plan['interception'] ?? ['active' => false];
        return [
            'status' => 'ok',
            'enabled' => (string)$model->general->shaper_enabled === '1',
            'dry_run' => (string)$model->general->shaper_dry_run === '1',
            /*
             * Whether this firewall can shape uploads at all. Reported even when
             * limits are off, so the interface can say so next to the upload field
             * rather than letting the user configure a cap and wait for nothing.
             */
            'upload_supported' => empty($interception['active'])
                || !empty($plan['upload_via_layer2']),
            /* True when uploads are shaped through the experimental layer2 path. */
            'upload_via_layer2' => !empty($plan['upload_via_layer2']),
            'interception' => $interception,
            'devices' => $rows,
        ];
    }

    /**
     * What the running shaper rules have actually matched.
     *
     * A limit that was accepted, saved and reported as applied can still shape
     * nothing, and until this existed the only way to find out was to measure the
     * traffic by hand. Read-only.
     */
    public function verifyAction(): array
    {
        $raw = (new Backend())->configdRun('wanquota shaperverify');
        $result = json_decode($raw, true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'rules' => [],
                    'error' => 'Could not read the running shaper rules'];
        }
        return $result;
    }

    /**
     * Services seen on the network that the catalog does not know yet.
     *
     * Read-only. Accepting one is a separate call, because accepting makes it
     * shapeable and shaping the wrong thing throttles traffic the household needs.
     */
    public function discoveredAction(): array
    {
        $backend = new Backend();
        if ($this->request->isPost() && $this->request->getPost('rescan')) {
            $backend->configdRun('wanquota discoveryscan thirty');
        }
        $result = json_decode($backend->configdRun('wanquota discoverylist'), true);
        if (!is_array($result)) {
            return ['status' => 'failed', 'services' => [],
                    'error' => 'Discovery data is unavailable'];
        }
        return $result;
    }

    /** Accept or ignore a discovered service. */
    public function decideAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $domain = preg_replace('/[^a-z0-9.\-]/', '', strtolower((string)$this->request->getPost('domain')));
        $decision = (string)$this->request->getPost('decision');
        if ($domain === '') {
            return ['status' => 'failed', 'error' => 'A domain is required'];
        }
        if (!in_array($decision, ['accept', 'ignore'], true)) {
            return ['status' => 'failed', 'error' => 'Decision must be accept or ignore'];
        }
        $backend = new Backend();
        $raw = $backend->configdRun('wanquota discovery' . $decision . ' ' . escapeshellarg($domain));
        $result = json_decode($raw, true);
        if (!is_array($result) || ($result['status'] ?? '') !== 'ok') {
            return ['status' => 'failed',
                    'error' => $result['error'] ?? 'The decision could not be recorded'];
        }
        /*
         * An accepted service joins the catalog, which changes what the plan matches,
         * so the plan is recomputed and applied. Without this the new service would sit
         * in the catalog capping nothing until something else triggered an apply.
         */
        if ($decision === 'accept') {
            $result['shaper'] = trim((string)$backend->configdRun('wanquota shapersync'));
        }
        return $result;
    }

    /** Save per-device limits and apply. */
    public function setDevicesAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $limits = [];
        $errors = [];
        $seen = [];
        foreach ((array)$this->request->getPost('limits') as $item) {
            $key = trim((string)($item['device'] ?? ''));
            if ($key === '') {
                continue;
            }
            if (isset($seen[strtolower($key)])) {
                $errors[] = sprintf('%s appears twice', $key);
                continue;
            }
            $seen[strtolower($key)] = true;
            $entry = ['device' => $key, 'enabled' => true];
            foreach (['mbit' => 'download', 'upload_mbit' => 'upload'] as $field => $label) {
                $value = trim((string)($item[$field] ?? ''));
                if ($value === '') {
                    continue;
                }
                if (!is_numeric($value) || (float)$value <= 0) {
                    $errors[] = sprintf('%s: %s rate must be a positive number', $key, $label);
                    continue 2;
                }
                $entry[$field] = (float)$value;
            }
            if (!isset($entry['mbit'])) {
                $errors[] = sprintf('%s: a download rate is required', $key);
                continue;
            }
            $limits[] = $entry;
        }
        if ($errors) {
            return ['status' => 'failed', 'errors' => $errors];
        }

        $model = new WanQuota();
        $model->general->device_limits_json = json_encode($limits);
        $this->applyState($model);
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save('Update WAN quota per-device limits');

        $backend = new Backend();
        $backend->configdRun('wanquota shaperplan');
        $applied = $backend->configdRun('wanquota shaperapply');
        return [
            'status' => 'ok',
            'saved' => count($limits),
            'dry_run' => (string)$model->general->shaper_dry_run === '1',
            'result' => trim((string)$applied),
        ];
    }

    /** Catalog, presets, current selections, and how many addresses each matched. */
    public function getAction(): array
    {
        $backend = new Backend();
        $catalog = json_decode($backend->configdRun('wanquota shapercatalog'), true);
        $plan = json_decode($backend->configdRun('wanquota shaperplan'), true);

        $model = new WanQuota();
        $configured = json_decode((string)$model->general->service_limits_json, true);
        $configured = is_array($configured) ? $configured : [];

        $selected = [];
        foreach ($configured as $item) {
            if (!empty($item['service'])) {
                $selected[(string)$item['service']] = $item;
            }
        }

        /* Address counts and refusals, keyed by service so a row can show its own. */
        $matched = [];
        foreach (($plan['pipes'] ?? []) as $entry) {
            $matched[$entry['service']] = [
                'addresses' => $entry['address_count'] ?? 0,
                'shared_excluded' => $entry['shared_excluded'] ?? 0,
            ];
        }
        $refused = [];
        foreach (($plan['rejected'] ?? []) as $entry) {
            $refused[$entry['service']] = $entry['reason'];
        }

        return [
            'status' => 'ok',
            'enabled' => (string)$model->general->shaper_enabled === '1',
            'dry_run' => (string)$model->general->shaper_dry_run === '1',
            'resolutions' => $catalog['resolutions'] ?? [],
            'services' => array_map(function ($service) use ($selected, $matched, $refused) {
                $key = $service['service'];
                $choice = $selected[$key] ?? null;
                return [
                    'service' => $key,
                    'label' => $service['label'],
                    'suffixes' => $service['suffixes'],
                    'selected' => $choice !== null && ($choice['enabled'] ?? true),
                    'resolution' => $choice['resolution'] ?? '',
                    'mbit' => $choice['mbit'] ?? '',
                    'matched' => $matched[$key] ?? null,
                    'refused' => $refused[$key] ?? null,
                ];
            }, $catalog['services'] ?? []),
        ];
    }

    /**
     * Save the selection and apply it.
     *
     * Only services present in the catalog are stored: a name typed by hand that
     * the backend would refuse anyway is rejected here, where the message can be
     * shown next to the control that caused it.
     */
    public function setAction(): array
    {
        if (!$this->request->isPost()) {
            return ['status' => 'failed', 'error' => 'POST required'];
        }
        $backend = new Backend();
        $catalog = json_decode($backend->configdRun('wanquota shapercatalog'), true);
        $known = [];
        foreach (($catalog['services'] ?? []) as $service) {
            $known[$service['service']] = true;
        }
        $presets = array_keys($catalog['resolutions'] ?? []);

        $limits = [];
        $errors = [];
        foreach ((array)$this->request->getPost('limits') as $item) {
            $key = (string)($item['service'] ?? '');
            if ($key === '' || empty($known[$key])) {
                $errors[] = sprintf('Unknown service: %s', $key === '' ? '(unnamed)' : $key);
                continue;
            }
            $entry = ['service' => $key, 'enabled' => true];
            $mbit = trim((string)($item['mbit'] ?? ''));
            $resolution = strtolower(trim((string)($item['resolution'] ?? '')));
            if ($mbit !== '') {
                if (!is_numeric($mbit) || (float)$mbit <= 0) {
                    $errors[] = sprintf('%s: rate must be a positive number', $key);
                    continue;
                }
                $entry['mbit'] = (float)$mbit;
            } elseif (in_array($resolution, $presets, true)) {
                $entry['resolution'] = $resolution;
            } else {
                $errors[] = sprintf('%s: choose a quality preset or enter a rate', $key);
                continue;
            }
            $limits[] = $entry;
        }
        if ($errors) {
            return ['status' => 'failed', 'errors' => $errors];
        }

        $model = new WanQuota();
        $model->general->service_limits_json = json_encode($limits);
        $this->applyState($model);
        $messages = $model->performValidation();
        if (count($messages) > 0) {
            $problems = [];
            foreach ($messages as $message) {
                $problems[] = (string)$message;
            }
            return ['status' => 'failed', 'errors' => $problems];
        }
        $model->serializeToConfig();
        \OPNsense\Core\Config::getInstance()->save('Update WAN quota per-service limits');

        /* Recompute the plan, then apply it. Apply is a no-op under dry-run. */
        $backend->configdRun('wanquota shaperplan');
        $applied = $backend->configdRun('wanquota shaperapply');

        return [
            'status' => 'ok',
            'saved' => count($limits),
            'dry_run' => (string)$model->general->shaper_dry_run === '1',
            'result' => trim((string)$applied),
        ];
    }
}
