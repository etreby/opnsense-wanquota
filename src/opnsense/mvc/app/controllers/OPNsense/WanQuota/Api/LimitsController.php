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
        $model->general->shaper_enabled = $this->request->getPost('enabled') ? '1' : '0';
        $model->general->shaper_dry_run = $this->request->getPost('dry_run') ? '1' : '0';
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
