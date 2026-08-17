#!/usr/local/bin/php
<?php

/*
 * Apply the per-service bandwidth plan to the OPNsense traffic shaper.
 *
 * The plan is computed in shaper.py; this only writes it into the TrafficShaper
 * model and asks OPNsense to reload. Going through the model rather than calling
 * ipfw directly is deliberate and not merely tidy: ipfw is not loaded on a stock
 * system, and loading it by hand installs a default deny rule that would cut all
 * traffic. OPNsense brings it up through the system's own rc scripts, which set
 * the accept default and synchronise the pf/ipfw load order. Only that path is
 * safe.
 *
 * Everything this creates is tagged with origin=wanquota, so a sync can replace
 * exactly what the plugin owns and never disturb a hand-made pipe or rule.
 */

require_once 'config.inc';
require_once 'util.inc';

const ORIGIN = 'wanquota';
const PLAN = '/var/db/wanquota/shaper-plan.json';


/*
 * Bring the shaper up the way OPNsense does.
 *
 * Two template namespaces drive it, and both gate their service on config:
 * OPNsense/IPFW renders /etc/rc.conf.d/ipfw with firewall_enable, and
 * OPNsense/Shaper renders /etc/rc.conf.d/dnctl with dnctl_enable. Writing pipes
 * and rules into the configuration does not flip either, so until both are
 * re-rendered rc still believes the services are disabled: ipfw refuses to start
 * and dnctl never loads dummynet, which leaves the rule referring to a pipe that
 * does not exist. That is a rule matching nothing while appearing configured.
 *
 * start.sh with no argument starts dnctl and then ipfw, which is the order the
 * system's own service definitions use.
 */
function reload_shaper(): void
{
    $backend = new OPNsense\Core\Backend();
    $backend->configdRun('template reload OPNsense/IPFW');
    $backend->configdRun('template reload OPNsense/Shaper');
    $backend->configdRun('ipfw reload');
    // start.sh is the supported entry point and handles both services.
    exec('/usr/local/opnsense/scripts/shaper/start.sh 2>&1', $ignored, $status);
}

/*
 * Delete the pipes this plugin created from the running dummynet state.
 *
 * Removing a pipe from the configuration and disabling the service does not
 * delete it from the kernel: it lingers with no rule pointing at it, shaping
 * nothing but visible in `ipfw pipe show` and confusing anyone looking for why a
 * limit seems to still exist. Deleting by number only touches pipes in this
 * plugin's reserved range.
 */
function delete_pipes(array $numbers): void
{
    foreach ($numbers as $number) {
        exec('/sbin/ipfw pipe ' . escapeshellarg((string)$number) . ' delete 2>/dev/null',
             $ignored, $status);
    }
}

$mode = $argv[1] ?? 'apply';

/*
 * Applying runs in two processes, not two passes.
 *
 * A rule's target is a ModelRelationField whose option list is resolved once per
 * request. A pipe saved earlier in the same process is not in it, so a rule
 * referring to that pipe fails validation with "Related pipe or queue not found"
 * even though the pipe is on disk. Re-instantiating the model does not help;
 * only a fresh process sees it. So 'apply' writes the pipes and then re-execs
 * itself to write the rules.
 */
if ($mode === 'apply') {
    $self = escapeshellarg(__FILE__);
    passthru('/usr/local/bin/php ' . $self . ' pipes', $pipeStatus);
    if ($pipeStatus !== 0) {
        exit($pipeStatus);
    }
    passthru('/usr/local/bin/php ' . $self . ' rules', $ruleStatus);
    exit($ruleStatus);
}

$model = new OPNsense\TrafficShaper\TrafficShaper();

/* Remove only what previous runs created. Rules go first: they reference pipes. */
$removed = 0;
$ownedNumbers = [];
foreach ($model->pipes->pipe->iterateItems() as $node) {
    if ((string)$node->origin === ORIGIN) {
        $ownedNumbers[] = (string)$node->number;
    }
}
$toRemove = ($mode === 'rules') ? [] : ['rules' => 'rule', 'pipes' => 'pipe'];
foreach ($toRemove as $set => $item) {
    $uuids = [];
    foreach ($model->$set->$item->iterateItems() as $node) {
        if ((string)$node->origin === ORIGIN) {
            $uuids[] = $node->getAttributes()['uuid'];
        }
    }
    foreach ($uuids as $uuid) {
        if ($model->$set->$item->del($uuid)) {
            $removed++;
        }
    }
}

if ($mode === 'flush') {
    $model->serializeToConfig();
    OPNsense\Core\Config::getInstance()->save('Remove WAN quota per-service bandwidth limits');
    reload_shaper();
    delete_pipes($ownedNumbers);
    echo json_encode(['status' => 'ok', 'removed' => $removed,
                      'pipes_deleted' => $ownedNumbers]) . PHP_EOL;
    exit(0);
}

$plan = @json_decode((string)@file_get_contents(PLAN), true);
if (!is_array($plan)) {
    fwrite(STDERR, "No usable plan at " . PLAN . "; run shaper.py first\n");
    exit(1);
}
if (($plan['status'] ?? '') !== 'ok' || !empty($plan['dry_run'])) {
    // Nothing to apply: either disabled, or a dry run whose whole purpose is to
    // change nothing. The removal above still runs, so turning the feature off or
    // switching to dry-run releases any limit already in place.
    $model->serializeToConfig();
    OPNsense\Core\Config::getInstance()->save('WAN quota per-service limits released');
    reload_shaper();
    /*
     * Deleting the pipes from the configuration does not remove them from the
     * running kernel. Measured after turning limits off: the rules were gone but
     * `ipfw pipe list` still showed 22000 and 22500, so anyone checking whether the
     * limit had been released saw pipes that looked live. Nothing was being shaped —
     * no rule pointed at them — but leaving them is misleading and they accumulate.
     */
    delete_pipes($ownedNumbers);
    echo json_encode([
        'status' => $plan['status'] ?? 'unknown',
        'applied' => 0,
        'removed' => $removed,
        'dry_run' => !empty($plan['dry_run']),
    ]) . PHP_EOL;
    exit(0);
}

if ($mode === 'pipes') {
foreach ($plan['pipes'] ?? [] as $entry) {
    $pipe = $model->pipes->pipe->Add();
    $pipe->number = (string)$entry['pipe'];
    $pipe->enabled = '1';
    $pipe->bandwidth = (string)$entry['mbit'];
    $pipe->bandwidthMetric = 'Mbit';
    /*
     * Mask on the destination address so the cap applies per device rather than
     * to the service as a whole. Without it two televisions share one pipe and
     * both degrade, which reads as the limit being set too low.
     */
    $pipe->mask = 'dst-ip';
    $pipe->description = sprintf('WAN quota: %s limited to %s Mbit/s', $entry['label'], $entry['mbit']);
    $pipe->origin = ORIGIN;
}

/*
 * Device pipes. A download cap and an upload cap are separate pipes because they
 * shape opposite directions and dummynet applies a pipe to one direction at a time.
 */
foreach ($plan['device_pipes'] ?? [] as $entry) {
    $pipe = $model->pipes->pipe->Add();
    $pipe->number = (string)$entry['pipe'];
    $pipe->enabled = '1';
    $pipe->bandwidth = (string)$entry['mbit'];
    $pipe->bandwidthMetric = 'Mbit';
    $pipe->description = sprintf('WAN quota: %s download limited to %s Mbit/s',
        $entry['name'], $entry['mbit']);
    $pipe->origin = ORIGIN;
    if (!empty($entry['upload_pipe'])) {
        $up = $model->pipes->pipe->Add();
        $up->number = (string)$entry['upload_pipe'];
        $up->enabled = '1';
        $up->bandwidth = (string)$entry['upload_mbit'];
        $up->bandwidthMetric = 'Mbit';
        $up->description = sprintf('WAN quota: %s upload limited to %s Mbit/s',
            $entry['name'], $entry['upload_mbit']);
        $up->origin = ORIGIN;
    }
}

$messages = $model->performValidation();
if (count($messages) > 0) {
    $errors = [];
    foreach ($messages as $message) {
        $errors[] = (string)$message;
    }
    fwrite(STDERR, "Pipe validation failed; no change made:\n  " . implode("\n  ", $errors) . "\n");
    exit(1);
}
$model->serializeToConfig();
OPNsense\Core\Config::getInstance()->save('WAN quota per-service bandwidth pipes');
echo json_encode(['status' => 'ok', 'phase' => 'pipes',
                  'pipes' => count($plan['pipes'] ?? []),
                  'device_pipes' => count($plan['device_pipes'] ?? []),
                  'removed' => $removed]) . PHP_EOL;
exit(0);
}

/* Map pipe number to the uuid actually stored, so a rule can target it. */
$pipeUuids = [];
foreach ($model->pipes->pipe->iterateItems() as $node) {
    if ((string)$node->origin === ORIGIN) {
        $pipeUuids[(string)$node->number] = $node->getAttributes()['uuid'];
    }
}
$applied = [];
foreach ($plan['pipes'] ?? [] as $entry) {
    $uuid = $pipeUuids[(string)$entry['pipe']] ?? null;
    if ($uuid === null) {
        continue;
    }
    $rule = $model->rules->rule->Add();
    $rule->enabled = '1';
    $rule->sequence = (string)$entry['pipe'];
    $rule->interface = 'lan';
    /*
     * Download traffic leaves the firewall through the LAN interface, so the rule
     * matches 'out via <lan>' with the service as the source. Matching 'in' was
     * reasoned about rather than checked and could never fire: packets entering
     * the LAN interface come from local devices, which never carry the service's
     * source address. Measuring it was what showed the rule matching nothing.
     *
     * One rule on the LAN side also covers every provider at once, where a rule
     * per WAN would drift as providers are added.
     */
    $rule->direction = 'out';
    $rule->proto = 'ip';
    $rule->source = implode(',', $entry['addresses']);
    $rule->destination = 'any';
    $rule->target = $uuid;
    $rule->description = sprintf('WAN quota: %s', $entry['label']);
    $rule->origin = ORIGIN;
    $applied[] = ['service' => $entry['service'], 'mbit' => $entry['mbit'],
                  'addresses' => $entry['address_count']];
}

/*
 * Device rules. Download is traffic heading to the device, so it matches on the way
 * out of the LAN interface with the device as destination; upload is the reverse.
 * Getting this backwards produces a rule that can never fire, which is how the
 * service rules were wrong before being measured.
 */
$appliedDevices = [];
foreach ($plan['device_pipes'] ?? [] as $entry) {
    $downUuid = $pipeUuids[(string)$entry['pipe']] ?? null;
    if ($downUuid !== null) {
        $rule = $model->rules->rule->Add();
        $rule->enabled = '1';
        $rule->sequence = (string)$entry['pipe'];
        $rule->interface = 'lan';
        $rule->direction = 'out';
        $rule->proto = 'ip';
        $rule->source = 'any';
        $rule->destination = $entry['device'];
        $rule->target = $downUuid;
        $rule->description = sprintf('WAN quota: %s download', $entry['name']);
        $rule->origin = ORIGIN;
    }
    if (!empty($entry['upload_pipe'])) {
        $upUuid = $pipeUuids[(string)$entry['upload_pipe']] ?? null;
        if ($upUuid !== null) {
            $rule = $model->rules->rule->Add();
            $rule->enabled = '1';
            $rule->sequence = (string)$entry['upload_pipe'];
            $rule->interface = 'lan';
            $rule->direction = 'in';
            $rule->proto = 'ip';
            $rule->source = $entry['device'];
            $rule->destination = 'any';
            $rule->target = $upUuid;
            $rule->description = sprintf('WAN quota: %s upload', $entry['name']);
            $rule->origin = ORIGIN;
        }
    }
    $appliedDevices[] = ['device' => $entry['device'], 'name' => $entry['name'],
                         'mbit' => $entry['mbit'], 'upload_mbit' => $entry['upload_mbit']];
}

$messages = $model->performValidation();
if (count($messages) > 0) {
    $errors = [];
    foreach ($messages as $message) {
        $errors[] = (string)$message;
    }
    fwrite(STDERR, "Rule validation failed; pipes were saved but no rule was added:\n  "
        . implode("\n  ", $errors) . "\n");
    exit(1);
}

$model->serializeToConfig();
OPNsense\Core\Config::getInstance()->save('Apply WAN quota per-service bandwidth limits');
/*
 * Re-render the IPFW templates before restarting the service.
 *
 * /etc/rc.conf.d/ipfw is generated from a template that sets firewall_enable to
 * YES only when an enabled shaper rule exists. Writing the rule to the config is
 * not enough on its own: until the template is re-rendered, rc still considers
 * ipfw disabled and the reload script stops and flushes instead of starting, so
 * the pipes exist on paper and shape nothing. The GUI does this render as part of
 * saving; doing it by hand means doing it here too.
 */
reload_shaper();

echo json_encode([
    'status' => 'ok',
    'applied' => $applied,
    'applied_devices' => $appliedDevices,
    'removed' => $removed,
    'rejected' => $plan['rejected'] ?? [],
    'device_rejected' => $plan['device_rejected'] ?? [],
]) . PHP_EOL;
