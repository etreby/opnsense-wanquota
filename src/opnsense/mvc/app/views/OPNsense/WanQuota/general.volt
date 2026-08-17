<script src="{{ cache_safe('/ui/js/chart.umd.min.js') }}"></script>
<style>
.wq-shell{--wq-blue:#3b82f6;--wq-cyan:#06b6d4;--wq-green:#10b981;--wq-amber:#f59e0b;--wq-red:#ef4444;--wq-ink:#172033}.wq-hero{padding:24px;border-radius:14px;background:linear-gradient(135deg,#172033,#253656 60%,#1677a8);color:#fff;margin-bottom:18px;box-shadow:0 12px 30px rgba(23,32,51,.18)}.wq-hero h2{margin:0 0 5px;font-weight:700}.wq-hero p{margin:0;opacity:.8}.wq-version{margin-top:8px;font-size:11px;opacity:.65;letter-spacing:.3px}.wq-hero-tools{float:right;display:flex;gap:6px}.wq-hero-tools .btn{background:#ffffff18;color:#fff;border-color:#ffffff4d}.wq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin:16px 0}.wq-card{background:var(--background-color,#fff);border:1px solid rgba(128,128,128,.2);border-radius:12px;padding:16px;box-shadow:0 4px 16px rgba(23,32,51,.07)}.wq-card h3{font-size:15px;margin:0 0 12px;color:inherit}.wq-metric{font-size:26px;font-weight:700;line-height:1.1}.wq-muted{opacity:.68;font-size:12px}.wq-progress{height:8px;background:rgba(128,128,128,.18);border-radius:8px;overflow:hidden;margin:12px 0}.wq-progress span{display:block;height:100%;border-radius:8px;background:linear-gradient(90deg,var(--wq-blue),var(--wq-cyan))}.wq-chart{position:relative;height:290px}.wq-chart-sm{position:relative;height:180px}.wq-section{margin-top:22px}.wq-section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.wq-section-title h3{margin:0}.wq-health-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}.wq-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.wq-table-wrap{overflow-x:auto}.wq-card .table{margin-bottom:0}.wq-risk-on_track{color:var(--wq-green)}.wq-risk-watch{color:var(--wq-amber)}.wq-risk-high,.wq-risk-exceeded{color:var(--wq-red)}.wq-action-box{padding:10px 12px;border-left:4px solid var(--wq-blue);background:rgba(59,130,246,.08);border-radius:6px}.wq-wallboard .navbar,.wq-wallboard #maintabs,.wq-wallboard .wq-exact{display:none!important}.wq-wallboard .wq-chart{height:38vh}.wq-contrast .wq-card{border:2px solid currentColor;box-shadow:none}.wq-drill{cursor:pointer;border-bottom:1px dotted currentColor;text-decoration:none}.wq-drill:hover,.wq-drill:focus{text-decoration:none;border-bottom-style:solid}.wq-drill-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:12px 14px;margin-bottom:12px;border-left:4px solid var(--wq-blue);background:rgba(59,130,246,.08);border-radius:6px}.wq-drill-metric{text-align:right}.wq-share{height:8px;background:rgba(128,128,128,.18);border-radius:8px;overflow:hidden;min-width:60px}.wq-share span{display:block;height:100%;border-radius:8px}.wq-unattributed td{opacity:.7}.wq-switch{display:inline-flex;align-items:center;gap:7px;margin:0;font-weight:400;cursor:pointer}.wq-action-box{display:flex;align-items:center;flex-wrap:wrap;gap:10px}.wq-limit{display:flex;flex-direction:column;gap:8px}.wq-limit-head{display:flex;align-items:center;gap:9px}.wq-limit-head h3{margin:0;flex:1 1 auto;font-size:15px}.wq-limit-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.wq-limit-row select,.wq-limit-row input{max-width:132px}.wq-pill{display:inline-block;padding:1px 8px;border-radius:11px;font-size:11px;background:rgba(128,128,128,.18)}.wq-pill-ok{background:rgba(16,185,129,.18);color:var(--wq-green)}.wq-pill-warn{background:rgba(245,158,11,.18);color:var(--wq-amber)}.wq-limit-off{opacity:.55}.wq-steps{list-style:none;display:flex;flex-wrap:wrap;gap:6px;padding:0;margin:0 0 16px}.wq-steps li{display:flex;align-items:center;gap:7px;padding:7px 13px;border-radius:20px;background:rgba(128,128,128,.12);font-size:12px;cursor:pointer;white-space:nowrap}.wq-steps li span{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:rgba(128,128,128,.3);font-weight:700;font-size:11px}.wq-steps li.active{background:var(--wq-blue);color:#fff}.wq-steps li.active span{background:#ffffff35}.wq-steps li.done span{background:var(--wq-green);color:#fff}.wq-subtabs{margin-bottom:16px}.wq-subtabs>li>a{border-radius:20px;padding:7px 18px;font-size:13px}.wq-why{padding:14px 16px;border-left:4px solid var(--wq-blue);background:rgba(59,130,246,.08);border-radius:6px}.wq-why h3{margin:0 0 4px;font-size:17px}.wq-why ol{margin:10px 0 0 18px;padding:0}.wq-why li{margin:3px 0}.wq-why-tags{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.wq-shares{margin-top:10px;font-size:12px}.wq-share-row{display:flex;align-items:center;gap:8px;padding:2px 0}.wq-share-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}.wq-share-name{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wq-share-pct{font-weight:700;flex:0 0 auto}.wq-share-others .wq-share-name{opacity:.7;font-style:italic}.wq-live{margin:4px 0 0}.wq-live-row{display:flex;gap:12px;flex-wrap:wrap}.wq-live-card{flex:1 1 220px;padding:10px 14px;border:1px solid rgba(128,128,128,.2);border-radius:10px;background:var(--background-color,#fff)}.wq-live-name{font-weight:700;font-size:13px;margin-bottom:4px}.wq-live-pair{display:flex;gap:14px;font-variant-numeric:tabular-nums}.wq-live-down{color:var(--wq-blue);font-weight:700}.wq-live-up{color:var(--wq-green);font-weight:700}
@media(max-width:767px){.wq-hero{padding:18px}.wq-chart{height:240px}.wq-metric{font-size:22px}.wq-hero-tools{float:none;margin-bottom:12px}.wq-drill-metric{text-align:left}}
</style>
<div class="wq-shell">
<div class="wq-hero"><div class="wq-hero-tools"><button id="unitToggle" class="btn btn-sm" type="button">GB</button><button id="contrastToggle" class="btn btn-sm" type="button"><i class="fa fa-adjust"></i></button><button id="wallboardToggle" class="btn btn-sm" type="button"><i class="fa fa-television"></i></button></div><h2><i class="fa fa-tachometer"></i> {{ lang._('WAN Intelligence') }}</h2><p>{{ lang._('Quota health, traffic trends, consumers and domain attribution in one place.') }}</p><div class="wq-version" id="pluginVersion"></div></div>
<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#summary">{{ lang._('Summary') }}</a></li>
    <li><a data-toggle="tab" href="#consumers">{{ lang._('Consumers') }}</a></li>
    <li><a data-toggle="tab" href="#daily">{{ lang._('Daily history') }}</a></li>
    <li><a data-toggle="tab" href="#monthly">{{ lang._('Monthly history') }}</a></li>
    <li><a data-toggle="tab" href="#apps">{{ lang._('Apps') }}</a></li>
    <li><a data-toggle="tab" href="#limits">{{ lang._('Limits') }}</a></li>
    <li><a data-toggle="tab" href="#sessions">{{ lang._('Live sessions') }}</a></li>
    <li><a data-toggle="tab" href="#intelligence">{{ lang._('Intelligence') }}</a></li>
    <li><a data-toggle="tab" href="#health">{{ lang._('Data health') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>

<div class="tab-content content-box tab-content">
    <div id="summary" class="tab-pane fade in active"><div style="padding:16px"><div class="btn-group pull-right"><button id="exportSummaryCsv" class="btn btn-default" type="button"><i class="fa fa-download"></i> CSV</button><button id="exportSummaryJson" class="btn btn-default" type="button"><i class="fa fa-download"></i> JSON</button></div><div id="liveThroughput" class="wq-live"></div><div class="wq-grid" id="quotaCards"></div><div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Provider quota comparison') }}</h3><div class="wq-chart"><canvas id="quotaChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('Download and upload mix') }}</h3><div class="wq-chart"><canvas id="trafficMixChart"></canvas></div></div></div><div id="summaryReport" class="wq-section wq-table-wrap"></div></div></div>
    <div id="consumers" class="tab-pane fade">
        <div style="padding:16px">
            <div class="form-inline" style="margin-bottom:12px">
                <label for="consumerPeriod">{{ lang._('Period') }}:&nbsp;</label>
                <select id="consumerPeriod" class="form-control">
                    <option value="today">{{ lang._('Today') }}</option>
                    <option value="week">{{ lang._('Last 7 days') }}</option>
                    <option value="thirty" selected>{{ lang._('Last 30 days') }}</option>
                    <option value="month">{{ lang._('Current month') }}</option>
                </select>
                <button id="refreshConsumers" class="btn btn-primary" type="button">{{ lang._('Refresh') }}</button>
                <div class="btn-group"><button id="exportConsumersCsv" class="btn btn-default" type="button"><i class="fa fa-download"></i> CSV</button><button id="exportConsumersJson" class="btn btn-default" type="button"><i class="fa fa-download"></i> JSON</button></div>
            </div>
            <div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Top LAN consumers') }}</h3><div class="wq-chart"><canvas id="hostChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('Top attributed domains') }}</h3><div class="wq-chart"><canvas id="domainChart"></canvas></div></div></div>
            <div class="wq-section wq-table-wrap"><div id="hostConsumers"></div></div><div class="wq-section wq-table-wrap"><div id="domainConsumers"></div></div>
            <div id="domainCoverage"></div>
            <h3>{{ lang._('Per-WAN attributed traffic') }}</h3><div id="wanConsumers"></div>
            <div id="providerDrill" class="wq-section wq-table-wrap"></div>
            <h3>{{ lang._('Device and domain drill-down') }}</h3>
            <div class="form-inline" style="margin-bottom:10px">
                <label for="drillDevice">{{ lang._('Device') }}:&nbsp;</label><select id="drillDevice" class="form-control"><option value="">All devices</option></select>
                <label for="drillDomain" style="margin-left:10px">{{ lang._('Domain') }}:&nbsp;</label><select id="drillDomain" class="form-control"><option value="">All domains</option></select>
                <button id="drillClear" class="btn btn-default" type="button" style="margin-left:10px;display:none"><i class="fa fa-times"></i> {{ lang._('Clear') }}</button>
            </div>
            <p class="wq-muted">{{ lang._('Click any device or site above to see what it exchanged traffic with.') }}</p>
            <div id="deviceDomainMatrix"></div>
        </div>
    </div>
    <div id="daily" class="tab-pane fade"><div style="padding:16px"><div class="wq-card"><h3>{{ lang._('Daily traffic trend') }}</h3><div class="wq-chart"><canvas id="dailyChart"></canvas></div></div><div id="dailyReport" class="wq-section wq-table-wrap"></div></div></div>
    <div id="monthly" class="tab-pane fade"><div style="padding:16px"><div class="wq-card"><h3>{{ lang._('Monthly traffic trend') }}</h3><div class="wq-chart"><canvas id="monthlyChart"></canvas></div></div><div id="monthlyReport" class="wq-section wq-table-wrap"></div></div></div>
    <div id="apps" class="tab-pane fade"><div style="padding:16px">
        <div class="wq-grid">
          <div class="wq-card"><h3>{{ lang._('Apps breakdown') }}</h3><div class="wq-chart"><canvas id="appChart"></canvas></div></div>
          <div class="wq-card"><h3>{{ lang._('Top apps') }}</h3><div id="appShares" class="wq-shares"></div></div>
        </div>
        <div class="wq-section wq-table-wrap"><div id="appTable"></div></div>
        <div class="wq-section">
          <h3>{{ lang._('What is this domain?') }}</h3>
          <div class="wq-toolbar">
            <input id="explainInput" class="form-control" style="max-width:340px" placeholder="{{ lang._('e.g. ipv4-c001.ix.nflxvideo.net') }}">
            <button id="explainGo" class="btn btn-primary" type="button"><i class="fa fa-search"></i> {{ lang._('Identify') }}</button>
          </div>
          <div id="explainResult" class="wq-section"></div>
        </div>
        <div id="appDrill" class="wq-section wq-table-wrap"></div>
    </div></div>
    <div id="limits" class="tab-pane fade"><div style="padding:16px">
        <!--
            One pair of switches for the whole tab, deliberately outside the sub-tabs.
            There used to be a pair in each, both writing shaper_enabled and
            shaper_dry_run, so saving on one sub-tab applied that sub-tab's switch
            state to the other's limits. Saving a device limit while the device
            sub-tab's switch was unticked turned shaping off altogether: the service
            limits looked untouched but disabled, and no rules were installed.
            Per-service and per-device limits combine, so the switch that governs both
            belongs where it visibly governs both.
        -->
        <div class="wq-action-box" style="margin-bottom:14px">
          <label class="wq-switch"><input type="checkbox" id="limitEnabled"> <b>{{ lang._('Enable limits') }}</b></label>
          <label class="wq-switch" style="margin-left:18px"><input type="checkbox" id="limitDryRun"> {{ lang._('Dry run (record the plan, change nothing)') }}</label>
          <span class="wq-muted" style="margin-left:14px">{{ lang._('Applies to service and device limits together. Both kinds can be active at once.') }}</span>
        </div>
        <ul class="nav nav-pills wq-subtabs">
            <li class="active"><a href="#limitsService" data-toggle="tab">{{ lang._('By service') }}</a></li>
            <li><a href="#limitsDevice" data-toggle="tab">{{ lang._('By device') }}</a></li>
        </ul>
        <div class="tab-content">
        <div id="limitsService" class="tab-pane fade in active">
        <div class="wq-action-box" style="margin-bottom:14px">
          <input id="limitSearch" class="form-control" style="max-width:230px" placeholder="{{ lang._('Search services…') }}">
          <span id="limitCount" class="wq-muted"></span>
          <button id="saveLimits" class="btn btn-primary" style="margin-left:auto"><i class="fa fa-check"></i> {{ lang._('Save and apply') }}</button>
        </div>
        <div id="limitStatus"></div>
        <div class="wq-action-box" style="margin-bottom:12px">
          <b>{{ lang._('Discovered services') }}</b>
          <span class="wq-muted">{{ lang._('Found from observed DNS answers and attributed traffic on this firewall. Accepting one adds it to the catalogue so it can be limited.') }}</span>
          <button id="rescanDiscovery" class="btn btn-default" style="margin-left:auto"><i class="fa fa-search"></i> {{ lang._('Look again') }}</button>
        </div>
        <div id="discoveredServices" class="wq-table-wrap" style="margin-bottom:16px"></div>
        <div id="limitCards" class="wq-grid"></div>
        <p class="wq-muted">{{ lang._('A cap bounds what a player can sustain; it does not select a resolution. Coverage is partial: a device using encrypted DNS, a VPN or ECH is not matched and runs uncapped.') }}</p>
        </div>
        <div id="limitsDevice" class="tab-pane fade">
            <div class="wq-action-box" style="margin-bottom:14px">
              <input id="deviceLimitSearch" class="form-control" style="max-width:230px" placeholder="{{ lang._('Search devices…') }}">
              <span id="deviceLimitCount" class="wq-muted"></span>
              <button id="verifyLimits" class="btn btn-default" style="margin-left:auto"><i class="fa fa-stethoscope"></i> {{ lang._('Verify') }}</button>
              <button id="saveDeviceLimits" class="btn btn-primary"><i class="fa fa-check"></i> {{ lang._('Save and apply') }}</button>
            </div>
            <div id="deviceLimitCapability"></div>
            <div id="deviceLimitStatus"></div>
            <div id="limitVerify"></div>
            <div class="wq-table-wrap"><div id="deviceLimitTable"></div></div>
            <p class="wq-muted">{{ lang._('A device limit caps the rate to and from one device. Keying it on the MAC keeps it applying after DHCP changes the address; keying it on the address alone does not. The firewall itself can never be limited.') }}</p>
        </div>
        </div>
    </div></div>
    <div id="sessions" class="tab-pane fade"><div style="padding:16px">
        <div class="wq-toolbar" style="margin-bottom:12px">
          <button id="refreshSessions" class="btn btn-primary" type="button"><i class="fa fa-refresh"></i> {{ lang._('Refresh') }}</button>
          <input id="sessionSearch" class="form-control" placeholder="{{ lang._('Filter device, destination or service') }}">
          <span id="sessionSummary" class="wq-muted"></span>
        </div>
        <label class="wq-switch" style="margin-bottom:10px"><input type="checkbox" id="sessionAuto" checked> {{ lang._('Refresh every 5 seconds') }}</label>
        <div class="wq-section wq-table-wrap"><h3>{{ lang._('Devices by live usage') }}</h3><div id="sessionDevices"></div></div>
        <div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Live rate per device') }}</h3><div class="wq-chart-sm"><canvas id="sessionChart"></canvas></div></div></div>
        <div class="wq-section wq-table-wrap"><h3>{{ lang._('Open sessions') }}</h3><div id="sessionTable"></div></div>
    </div></div>
    <div id="intelligence" class="tab-pane fade"><div style="padding:16px"><div class="wq-toolbar"><label>Period</label><select id="intelligencePeriod" class="form-control"><option value="today">Today</option><option value="week">7 days</option><option value="thirty" selected>30 days</option><option value="month">Current month</option></select><input id="intelligenceSearch" class="form-control" placeholder="Filter groups, categories or anomalies"><button id="refreshIntelligence" class="btn btn-primary" type="button">Refresh</button></div><div id="intelligenceCards" class="wq-grid"></div><div class="wq-action-box wq-toolbar"><b>Temporary guardrail override</b><select id="overrideProvider" class="form-control"></select><select id="overrideMode" class="form-control"><option value="observe">Observe</option><option value="deprioritize">Deprioritize</option><option value="failover">Fail over</option><option value="cutoff">Cut off</option></select><select id="overrideHours" class="form-control"><option value="1">1 hour</option><option value="6">6 hours</option><option value="24" selected>24 hours</option><option value="168">7 days</option></select><button id="applyOverride" class="btn btn-warning" type="button">Apply override</button><span id="overrideStatus" class="wq-muted">Overrides remain advisory while enforcement is disabled or dry-run.</span></div><div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Device-group usage and budgets') }}</h3><div class="wq-chart"><canvas id="groupChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('App categories breakdown') }}</h3><div class="wq-chart"><canvas id="categoryChart"></canvas></div><div id="categoryShares" class="wq-shares"></div></div><div class="wq-card"><h3>{{ lang._('Traffic versus provider quality') }}</h3><div class="wq-chart"><canvas id="qualityChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('Cycle history') }}</h3><div class="wq-chart"><canvas id="cycleChart"></canvas></div></div></div><div id="categoryDrill" class="wq-section wq-table-wrap"></div><div id="intelligenceDetails" class="wq-section wq-table-wrap"></div></div></div>
    <div id="health" class="tab-pane fade"><div id="healthReport" style="padding:16px"></div></div>
    <div id="settings" class="tab-pane fade"><div style="padding:16px">
        <ol class="wq-steps" id="wizardSteps">
            <li data-step="0" class="active"><span>1</span> {{ lang._('Getting started') }}</li>
            <li data-step="1"><span>2</span> {{ lang._('WAN providers') }}</li>
            <li data-step="2"><span>3</span> {{ lang._('Reporting') }}</li>
            <li data-step="3"><span>4</span> {{ lang._('Alerts and delivery') }}</li>
            <li data-step="4"><span>5</span> {{ lang._('Intelligence and devices') }}</li>
            <li data-step="5"><span>6</span> {{ lang._('Enforcement and limits') }}</li>
        </ol>
        <!--
          Each step is a real <form> whose id is the mapper key plus a suffix.
          mapDataToFormUI iterates <form> elements and matches on the id up to the
          first hyphen, so a wrapper div is invisible to it: naming the steps
          frm_wanquota_settings-<step> is what makes one endpoint populate all six.
          The wrapper keeps its id because saveFormToEndpoint collects fields by
          descendant selector, so saving still gathers every step at once.
        -->
        <div id="frm_wanquota_settings">
            <div class="wq-step" data-step="0">
                <div class="wq-card"><h3>{{ lang._('Getting started') }}</h3>
                <p class="wq-muted">{{ lang._('What the plugin collects at all. Start here.') }}</p>
                {{ partial("layout_partials/base_form", ['fields':wizardBasics,'id':'frm_wanquota_settings-basics']) }}</div>
            </div>
            <div class="wq-step" data-step="1" style="display:none">
                <div class="wq-card"><h3>{{ lang._('WAN providers') }}</h3>
                <p class="wq-muted">{{ lang._('One entry per internet connection, with its allowance and billing day. Providers 3 and 4 are off by default.') }}</p>
                {{ partial("layout_partials/base_form", ['fields':wizardProviders,'id':'frm_wanquota_settings-providers']) }}</div>
            </div>
            <div class="wq-step" data-step="2" style="display:none">
                <div class="wq-card"><h3>{{ lang._('Reporting') }}</h3>
                <p class="wq-muted">{{ lang._('How much detail the reports show, and how long observations are kept.') }}</p>
                {{ partial("layout_partials/base_form", ['fields':wizardReporting,'id':'frm_wanquota_settings-reporting']) }}</div>
            </div>
            <div class="wq-step" data-step="3" style="display:none">
                <div class="wq-card"><h3>{{ lang._('Alerts and delivery') }}</h3>
                <p class="wq-muted">{{ lang._('When to warn, and where to send it. Webhooks are HTTPS only; SMTP uses STARTTLS.') }}</p>
                {{ partial("layout_partials/base_form", ['fields':wizardAlerts,'id':'frm_wanquota_settings-alerts']) }}</div>
            </div>
            <div class="wq-step" data-step="4" style="display:none">
                <div class="wq-card"><h3>{{ lang._('Intelligence and devices') }}</h3>
                <p class="wq-muted">{{ lang._('Forecasts, anomaly detection, and per-device grouping. A per-device policy may key on address, MAC or DHCP hostname; MAC survives a DHCP change.') }}</p>
                {{ partial("layout_partials/base_form", ['fields':wizardIntelligence,'id':'frm_wanquota_settings-intelligence']) }}</div>
            </div>
            <div class="wq-step" data-step="5" style="display:none">
                <div class="wq-card"><h3>{{ lang._('Enforcement and limits') }}</h3>
                <div class="alert alert-warning">{{ lang._('These are the only settings that change how traffic flows. Every one defaults to off, and to dry-run when first enabled. Per-service rates are set in the Limits tab.') }}</div>
                {{ partial("layout_partials/base_form", ['fields':wizardEnforcement,'id':'frm_wanquota_settings-enforcement']) }}</div>
            </div>
        </div>
        <div class="wq-toolbar" style="margin-top:14px">
            <button class="btn btn-default" id="wizardBack" type="button"><i class="fa fa-arrow-left"></i> {{ lang._('Back') }}</button>
            <button class="btn btn-default" id="wizardNext" type="button">{{ lang._('Next') }} <i class="fa fa-arrow-right"></i></button>
            <button class="btn btn-primary" id="saveAct" type="button" style="margin-left:auto"><b>{{ lang._('Save') }}</b> <i id="saveAct_progress"></i></button>
        </div>
        <p class="wq-muted">{{ lang._('Save applies every step, not just the one on screen.') }}</p>
    </div></div>
</div>
</div>

<script>
let wqUnit='GB';
function gb(value) { const divisor=wqUnit==='MB'?1000000:1000000000; return (Number(value || 0) / divisor).toFixed(wqUnit==='MB'?1:3) + ' ' + wqUnit; }
function esc(value) { return $('<div>').text(value ?? '').html(); }
const wqCharts = {};
const wqColors = ['#3b82f6','#06b6d4','#10b981','#f59e0b','#8b5cf6','#ef4444','#64748b'];
function makeChart(id, config) { if (wqCharts[id]) wqCharts[id].destroy(); const canvas=document.getElementById(id); if(canvas) wqCharts[id]=new Chart(canvas,config); }
function chartOptions(horizontal=false) { return {responsive:true,maintainAspectRatio:false,indexAxis:horizontal?'y':'x',plugins:{legend:{display:true,position:'bottom'}},scales:{x:{beginAtZero:true,grid:{color:'rgba(128,128,128,.12)'}},y:{beginAtZero:true,grid:{color:'rgba(128,128,128,.12)'}}}}; }
/* A bit rate at whatever scale it is, so a quiet link is not shown as 0.00 Mbit/s. */
function rate(bps) {
    const value = Number(bps) || 0;
    if (value >= 1e9) return (value / 1e9).toFixed(2) + ' Gbit/s';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + ' Mbit/s';
    if (value >= 1e3) return (value / 1e3).toFixed(1) + ' kbit/s';
    return value + ' bit/s';
}
/*
 * Live throughput per WAN, polled while the Summary tab is visible.
 *
 * The quota cards answer "how much this cycle" and cannot answer "what is moving now",
 * because vnStat and the flow database both aggregate after the fact. This reads the
 * interface counters, so the direction split is exact — unlike the per-WAN attribution
 * report, which explicitly cannot split direction. Polling stops when the tab is not
 * visible: each call samples for a second on the firewall.
 */
let livePoll = null;
function renderLiveThroughput(data) {
    if (data.status !== 'ok' || !(data.wans || []).length) {
        $('#liveThroughput').empty();
        return;
    }
    let html = '<div class="wq-live-row">';
    for (const wan of data.wans) {
        if (!wan.available) {
            html += '<div class="wq-live-card"><div class="wq-live-name">' + esc(wan.name)
                 +  '</div><div class="wq-muted">' + esc(wan.reason || 'unavailable')
                 +  '</div></div>';
            continue;
        }
        html += '<div class="wq-live-card">'
             +  '<div class="wq-live-name">' + esc(wan.name)
             +  ' <small class="wq-muted">' + esc(wan.interface) + '</small></div>'
             +  '<div class="wq-live-pair">'
             +  '<span class="wq-live-down" title="' + esc('Download') + '">&#9660; '
             +  esc(rate(wan.download_bps)) + '</span>'
             +  '<span class="wq-live-up" title="' + esc('Upload') + '">&#9650; '
             +  esc(rate(wan.upload_bps)) + '</span>'
             +  '</div></div>';
    }
    html += '</div>';
    $('#liveThroughput').html(html);
}
function pollThroughput() {
    ajaxCall('/api/wanquota/report/throughput', {}, renderLiveThroughput);
}
function startThroughput() {
    if (livePoll) return;
    pollThroughput();
    livePoll = setInterval(function() {
        // Stop polling if the tab is hidden: the sample costs a second on the firewall.
        if (!$('#summary').hasClass('active')) { stopThroughput(); return; }
        pollThroughput();
    }, 4000);
}
function stopThroughput() {
    if (livePoll) { clearInterval(livePoll); livePoll = null; }
}
function quotaCards(data) { return (data.providers||[]).map((p,i)=>{const pct=Math.min(100,Number(p.percent||0)), color=pct>=90?'#ef4444':pct>=75?'#f59e0b':wqColors[i%wqColors.length];return `<div class="wq-card"><div class="wq-muted">${esc(p.logical_interface)} → ${esc(p.interface)}</div><h3><a href="#" class="wq-drill" data-drill="provider" data-value='${esc(p.name)}' title="Show which devices use this WAN most">${esc(p.name)}</a></h3><div class="wq-metric">${pct.toFixed(1)}%</div><div class="wq-progress"><span style="width:${pct}%;background:${color}"></span></div><div><b>${gb(p.remaining)}</b> remaining</div><div class="wq-muted">${esc(p.days_left)} days left · ${gb(p.daily_budget)}/day budget</div></div>`}).join(''); }
function renderPluginVersion(data){const v=data&&data.plugin_version;$('#pluginVersion').text(v?('os-wanquota '+v):'');}
function renderSummaryCharts(data){renderPluginVersion(data);const p=data.providers||[];$('#quotaCards').html(quotaCards(data));makeChart('quotaChart',{type:'bar',data:{labels:p.map(x=>x.name),datasets:[{label:'Used GB',data:p.map(x=>x.used/1e9),backgroundColor:wqColors},{label:'Remaining GB',data:p.map(x=>x.remaining/1e9),backgroundColor:'rgba(128,128,128,.25)'}]},options:chartOptions(false)});makeChart('trafficMixChart',{type:'doughnut',data:{labels:p.flatMap(x=>[x.name+' download',x.name+' upload']),datasets:[{data:p.flatMap(x=>[x.rx/1e9,x.tx/1e9]),backgroundColor:p.flatMap((x,i)=>[wqColors[i%wqColors.length],wqColors[(i+3)%wqColors.length]])}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}});}
function renderConsumerCharts(data){const hosts=(data.hosts||[]).slice(0,10),domains=(data.domains||[]).slice(0,10),hostOptions=chartOptions(true),domainOptions=chartOptions(true);hostOptions.onClick=(event,elements)=>{if(elements.length)drillTo('device',hosts[elements[0].index].ip);};domainOptions.onClick=(event,elements)=>{if(elements.length)drillTo('domain',domains[elements[0].index].domain);};makeChart('hostChart',{type:'bar',data:{labels:hosts.map(x=>x.name),datasets:[{label:'Download GB',data:hosts.map(x=>x.download/1e9),backgroundColor:'#3b82f6'},{label:'Upload GB',data:hosts.map(x=>x.upload/1e9),backgroundColor:'#06b6d4'}]},options:hostOptions});makeChart('domainChart',{type:'bar',data:{labels:domains.map(x=>x.domain),datasets:[{label:'Attributed GB',data:domains.map(x=>x.total/1e9),backgroundColor:'#8b5cf6'}]},options:domainOptions});}
function renderHistoryChart(id,data){const dates=[...new Set((data.providers||[]).flatMap(p=>p.rows.map(r=>r.date)))].sort();makeChart(id,{type:'line',data:{labels:dates,datasets:(data.providers||[]).map((p,i)=>({label:p.name+' total GB',data:dates.map(d=>{const r=p.rows.find(x=>x.date===d);return r?r.total/1e9:null}),borderColor:wqColors[i%wqColors.length],backgroundColor:wqColors[i%wqColors.length]+'33',fill:true,tension:.3,pointRadius:2}))},options:chartOptions(false)});}
function downloadReport(filename, content, type) {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([content], {type: type}));
    link.download = filename;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
function csvCell(value) { let text=String(value ?? ''); if (/^[=+\-@]/.test(text)) text="'"+text; return '"' + text.replace(/"/g, '""') + '"'; }
function csvDocument(headers, rows) {
    return '\uFEFF' + [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}
function summaryTable(data) {
    if (!data || !data.providers) return '<div class="alert alert-danger">Report unavailable</div>';
    let html = '<table class="table table-striped"><thead><tr><th>{{ lang._('Provider') }}</th><th>{{ lang._('Cycle') }}</th><th>{{ lang._('Download') }}</th><th>{{ lang._('Upload') }}</th><th>{{ lang._('Used') }}</th><th>{{ lang._('Remaining') }}</th><th>{{ lang._('Daily budget') }}</th><th>{{ lang._('Projected') }}</th></tr></thead><tbody>';
    for (const item of data.providers) {
        const style = item.warning ? ' class="danger"' : '';
        const status = item.available ? '' : '<br><small class="text-danger">' + esc(item.error) + '</small>';
        html += `<tr${style}><td><b>${esc(item.name)}</b><br><small>${esc(item.logical_interface)} → ${esc(item.interface)}</small>${status}</td><td>${item.start}<br>${item.end}</td><td>${gb(item.rx)}</td><td>${gb(item.tx)}</td><td>${gb(item.used)} (${Number(item.percent).toFixed(2)}%)</td><td>${gb(item.remaining)}</td><td>${gb(item.daily_budget)}</td><td>${gb(item.projected)}</td></tr>`;
    }
    return html + '</tbody></table><small>Generated: ' + esc(data.generated_at) + '</small>';
}
function historyTable(data) {
    if (!data || !data.providers) return '<div class="alert alert-danger">Report unavailable</div>';
    let html = '';
    for (const provider of data.providers) {
        html += '<h3>' + esc(provider.name) + '</h3><table class="table table-condensed table-striped"><thead><tr><th>{{ lang._('Date') }}</th><th>{{ lang._('Download') }}</th><th>{{ lang._('Upload') }}</th><th>{{ lang._('Total') }}</th></tr></thead><tbody>';
        for (const row of provider.rows) html += `<tr><td>${row.date}</td><td>${gb(row.rx)}</td><td>${gb(row.tx)}</td><td>${gb(row.total)}</td></tr>`;
        html += '</tbody></table>';
    }
    return html;
}
function consumerTable(rows, key) {
    if (!rows || !rows.length) return '<div class="alert alert-info">No traffic data is available for this period.</div>';
    let html = key === 'name'
        ? '<table class="table table-striped"><thead><tr><th>{{ lang._('Device') }}</th><th>{{ lang._('Download') }}</th><th>{{ lang._('Upload') }}</th><th>{{ lang._('Total') }}</th></tr></thead><tbody>'
        : '<table class="table table-striped"><thead><tr><th>{{ lang._('Attributed domain') }}</th><th>{{ lang._('Observed IPs') }}</th><th>{{ lang._('Attributed total') }}</th></tr></thead><tbody>';
    for (const row of rows) {
        if (key === 'name') {
            html += `<tr><td><a href="#" class="wq-drill" data-drill="device" data-value='${esc(row.ip)}' title="Show the sites this device used"><b>${esc(row.name)}</b></a><br><small>${esc(row.ip)}</small></td><td>${gb(row.download)}</td><td>${gb(row.upload)}</td><td><b>${gb(row.total)}</b></td></tr>`;
        } else {
            html += `<tr><td><a href="#" class="wq-drill" data-drill="domain" data-value='${esc(row.domain)}' title="Show the devices that used this site"><b>${esc(row.domain)}</b></a> <a href="#" class="wq-drill wq-muted" data-drill="explain" data-value='${esc(row.domain)}' title="Identify this domain">{{ lang._('why?') }}</a></td><td>${row.ip_count}</td><td><b>${gb(row.total)}</b></td></tr>`;
        }
    }
    return html + '</tbody></table>';
}
let currentSummaryData = null, currentConsumerData = null;
let currentIntelligenceData = null;
function intelligenceCards(data){const providers=data?.summary?.providers||[];return providers.map(p=>{const f=p.forecast||{},q=p.quality||{},policy=p.policy||{},movement=p.movement;const trend=movement?(movement.used_delta>=0?'▲ ':'▼ ')+gb(Math.abs(movement.used_delta))+' in 24h':'Collecting 24h comparison';return `<div class="wq-card" data-filter="${esc((p.name+' '+f.risk+' '+policy.recommended).toLowerCase())}"><div class="wq-muted">${esc(p.logical_interface)} · ${esc(q.status||'unknown')}</div><h3><a href="#" class="wq-drill" data-drill="provider" data-value='${esc(p.name)}' title="Show which devices use this WAN most">${esc(p.name)}</a></h3><div class="wq-metric wq-risk-${esc(f.risk||'on_track')}">${esc((f.risk||'unknown').replace('_',' ').toUpperCase())}</div><div>${f.exhaustion_date?'Exhaustion '+esc(f.exhaustion_date):'Projected within allowance'}</div><div><b>${esc(trend)}</b></div><div class="wq-muted">Latency ${Number(q.latency||0).toFixed(1)} ms · Loss ${Number(q.loss||0).toFixed(1)}% · Guardrail ${esc(policy.recommended||'observe')} ${policy.dry_run?'(dry-run)':''}</div></div>`}).join('');}
function intelligenceDetails(data){const anomalies=data.anomalies||[],archives=data.archives||[],patterns=data.patterns||[],domains=(data?.consumers?.domains||[]).slice(0,30);let html='<h3>{{ lang._('Domain intelligence') }}</h3><table class="table table-striped"><thead><tr><th>{{ lang._('Domain') }}</th><th>{{ lang._('Category') }}</th><th>{{ lang._('Traffic') }}</th><th>{{ lang._('First seen') }}</th><th>{{ lang._('Last seen') }}</th></tr></thead><tbody>';for(const d of domains)html+=`<tr data-filter="${esc((d.domain+' '+d.category).toLowerCase())}"><td><b>${esc(d.domain)}</b></td><td>${esc(d.category||'Other')}</td><td>${gb(d.total)}</td><td>${d.first_seen?new Date(d.first_seen*1000).toLocaleString():'—'}</td><td>${d.last_seen?new Date(d.last_seen*1000).toLocaleString():'—'}</td></tr>`;html+='</tbody></table><h3>{{ lang._('Recent anomalies') }}</h3><table class="table table-striped"><thead><tr><th>{{ lang._('Time') }}</th><th>{{ lang._('Severity') }}</th><th>{{ lang._('Subject') }}</th><th>{{ lang._('Finding') }}</th></tr></thead><tbody>';for(const a of anomalies)html+=`<tr data-filter="${esc((a.subject+' '+a.kind+' '+a.severity).toLowerCase())}"><td>${new Date(a.ts*1000).toLocaleString()}</td><td><span class="label label-${a.severity==='critical'?'danger':'warning'}">${esc(a.severity)}</span></td><td>${esc(a.subject)}</td><td>${esc(a.message)}</td></tr>`;html+='</tbody></table><h3>{{ lang._('Weekday / weekend pattern') }}</h3><table class="table table-striped"><thead><tr><th>{{ lang._('Provider') }}</th><th>{{ lang._('Average weekday') }}</th><th>{{ lang._('Average weekend day') }}</th></tr></thead><tbody>';for(const p of patterns)html+=`<tr data-filter="${esc(p.provider.toLowerCase())}"><td>${esc(p.provider)}</td><td>${gb(p.weekday_average)}</td><td>${gb(p.weekend_average)}</td></tr>`;html+='</tbody></table><h3>{{ lang._('Completed billing cycles') }}</h3><table class="table table-striped"><thead><tr><th>{{ lang._('Provider') }}</th><th>{{ lang._('Cycle') }}</th><th>{{ lang._('Used') }}</th><th>{{ lang._('Quota') }}</th><th>{{ lang._('Utilization') }}</th></tr></thead><tbody>';for(const a of archives)html+=`<tr data-filter="${esc(a.provider.toLowerCase())}"><td>${esc(a.provider)}</td><td>${esc(a.start)} → ${esc(a.end)}</td><td>${gb(a.used)}</td><td>${gb(a.quota)}</td><td>${(a.used/a.quota*100).toFixed(1)}%</td></tr>`;return html+'</tbody></table>';}
function categoryPalette(count) {
    // Repeat the accent palette rather than generating random hues, so a category
    // keeps the same colour between the chart and the share list beneath it.
    const out = [];
    for (let i = 0; i < count; i++) out.push(wqColors[i % wqColors.length]);
    return out;
}
function renderCategoryBreakdown(data) {
    const breakdown = data && data.category_breakdown;
    const rows = (breakdown && breakdown.categories) || [];
    if (!rows.length) {
        $('#categoryShares').html('<div class="wq-muted">' + esc('No attributed traffic to categorise for this period.') + '</div>');
        makeChart('categoryChart', {type:'pie', data:{labels:[],datasets:[{data:[]}]}, options:{responsive:true,maintainAspectRatio:false}});
        return;
    }
    const colors = categoryPalette(rows.length);
    const chartOpts = {
        responsive:true, maintainAspectRatio:false,
        plugins:{
            legend:{display:false},
            tooltip:{callbacks:{label:(ctx)=>{
                const row = rows[ctx.dataIndex];
                return ' ' + row.name + ' — ' + row.percent.toFixed(1) + '% (' + gb(row.total) + ')';
            }}}
        }
    };
    chartOpts.onClick = (event, elements) => {
        if (elements.length) showCategory(rows[elements[0].index].name);
    };
    makeChart('categoryChart', {
        type:'pie',
        data:{labels:rows.map(r=>r.name),datasets:[{data:rows.map(r=>r.total),backgroundColor:colors,borderWidth:0}]},
        options: chartOpts
    });
    let html = '<div class="wq-muted" style="margin-bottom:6px">' + esc('Top ' + (breakdown.top_n || 10)) + '</div>';
    rows.forEach((row, index) => {
        const others = row.name === 'Others' || row.name === 'Uncategorised';
        const folded = row.categories_folded ? ' (' + row.categories_folded + ')' : '';
        const clickable = row.name !== 'Others';
        html += '<div class="wq-share-row' + (others ? ' wq-share-others' : '') + '">'
             +  '<span class="wq-share-dot" style="background:' + colors[index] + '"></span>'
             +  '<span class="wq-share-name">'
             +  (clickable
                 ? '<a href="#" class="wq-drill" data-drill="category" data-value=\'' + esc(row.name) + '\'>' + esc(row.name) + '</a>'
                 : esc(row.name + folded))
             +  '</span>'
             +  '<span class="wq-muted">' + gb(row.total) + '</span>'
             +  '<span class="wq-share-pct">' + row.percent.toFixed(1) + '%</span>'
             +  '</div>';
    });
    if (breakdown.note) html += '<div class="wq-muted" style="margin-top:8px">' + esc(breakdown.note) + '</div>';
    $('#categoryShares').html(html);
}

function categoryDetail(name) {
    // Built from the payload already loaded for this tab: every domain carries its
    // category and the device/domain matrix is present, so no extra request.
    const consumer = (currentIntelligenceData && currentIntelligenceData.consumers) || {};
    const wanted = String(name || '').toLowerCase();
    const domains = (consumer.domains || []).filter(d => String(d.category || '').toLowerCase() === wanted)
        .sort((a, b) => b.total - a.total);
    const names = new Set(domains.map(d => d.domain));
    const devices = {};
    for (const row of consumer.device_domains || []) {
        if (!names.has(row.domain)) continue;
        const entry = devices[row.device] || (devices[row.device] = {device: row.device, name: row.name, total: 0, domains: 0});
        entry.total += row.total;
        entry.domains += 1;
    }
    return {
        domains,
        devices: Object.values(devices).sort((a, b) => b.total - a.total),
        total: domains.reduce((sum, d) => sum + d.total, 0),
    };
}
function showCategory(name) {
    if (!name || name === 'Others') return;
    const detail = categoryDetail(name);
    const breakdown = (currentIntelligenceData && currentIntelligenceData.category_breakdown) || {};
    const share = (breakdown.categories || []).find(c => c.name === name);
    let html = drillHeader(name, 'what this category is made of',
        gb(detail.total), share ? share.percent.toFixed(1) + '% of attributed traffic' : 'attributed traffic');
    html += '<button id="categoryClear" class="btn btn-default btn-sm" style="margin-bottom:10px"><i class="fa fa-times"></i> '
         +  '{{ lang._("Clear") }}</button>';
    if (!detail.domains.length) {
        return $('#categoryDrill').html(html + '<div class="alert alert-info">'
            + esc('No attributed traffic in this category for this period.') + '</div>');
    }
    const top = detail.domains[0].total || 1;
    html += '<div class="wq-grid"><div class="wq-card"><h3>{{ lang._("Sites in this category") }}</h3>'
         +  '<table class="table table-condensed table-striped"><thead><tr><th>{{ lang._("Site") }}</th>'
         +  '<th style="width:28%">{{ lang._("Share") }}</th><th>{{ lang._("Traffic") }}</th></tr></thead><tbody>';
    for (const d of detail.domains) {
        html += '<tr><td><a href="#" class="wq-drill" data-drill="domain" data-value=\'' + esc(d.domain) + '\'>'
             +  esc(d.domain) + '</a></td><td>' + shareBar(d.total / top, '#8b5cf6') + '</td><td><b>'
             +  gb(d.total) + '</b></td></tr>';
    }
    html += '</tbody></table></div><div class="wq-card"><h3>{{ lang._("Devices using it") }}</h3>';
    if (!detail.devices.length) {
        html += '<div class="wq-muted">' + esc('No device could be attributed to these sites.') + '</div>';
    } else {
        const topDevice = detail.devices[0].total || 1;
        html += '<table class="table table-condensed table-striped"><thead><tr><th>{{ lang._("Device") }}</th>'
             +  '<th style="width:28%">{{ lang._("Share") }}</th><th>{{ lang._("Traffic") }}</th></tr></thead><tbody>';
        for (const dev of detail.devices) {
            html += '<tr><td><a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(dev.device) + '\'>'
                 +  '<b>' + esc(dev.name) + '</b></a><br><small class="wq-muted">' + esc(dev.device)
                 +  ' · ' + dev.domains + ' {{ lang._("site(s)") }}</small></td><td>'
                 +  shareBar(dev.total / topDevice, '#3b82f6') + '</td><td><b>' + gb(dev.total) + '</b></td></tr>';
        }
        html += '</tbody></table>';
    }
    html += '</div></div><div class="wq-muted">'
         +  esc('Device totals count only this category\'s sites, so they are not each device\'s overall usage. They can sum to less than the category total, because the device/site matrix is capped and a site counted here may have no matrix row.')
         +  '</div>';
    $('#categoryDrill').html(html);
    document.getElementById('categoryDrill').scrollIntoView({behavior: 'smooth', block: 'start'});
}

function renderApps(data) {
    const breakdown = data && data.app_breakdown;
    const rows = (breakdown && breakdown.apps) || [];
    if (!rows.length) {
        $('#appShares').html('<div class="wq-muted">' + esc('No attributed traffic to break down for this period.') + '</div>');
        $('#appTable').empty();
        return;
    }
    const colors = categoryPalette(rows.length);
    makeChart('appChart', {
        type: 'pie',
        data: {labels: rows.map(r => r.name), datasets: [{data: rows.map(r => r.total), backgroundColor: colors, borderWidth: 0}]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {legend: {display: false}, tooltip: {callbacks: {label: ctx => {
                const row = rows[ctx.dataIndex];
                return ' ' + row.name + ' — ' + row.percent.toFixed(1) + '% (' + gb(row.total) + ')';
            }}}},
            onClick: (event, elements) => { if (elements.length) showApp(rows[elements[0].index].name); }
        }
    });
    let shares = '<div class="wq-muted" style="margin-bottom:6px">' + esc('Top ' + (breakdown.top_n || 10)) + '</div>';
    rows.forEach((row, index) => {
        const rollup = row.name === 'Others';
        const folded = row.apps_folded ? ' (' + row.apps_folded + ')' : '';
        shares += '<div class="wq-share-row' + (rollup ? ' wq-share-others' : '') + '">'
               +  '<span class="wq-share-dot" style="background:' + colors[index] + '"></span>'
               +  '<span class="wq-share-name">'
               +  (rollup ? esc(row.name + folded)
                          : '<a href="#" class="wq-drill" data-drill="app" data-value=\'' + esc(row.name) + '\'>' + esc(row.name) + '</a>')
               +  '</span><span class="wq-muted">' + gb(row.total) + '</span>'
               +  '<span class="wq-share-pct">' + row.percent.toFixed(1) + '%</span></div>';
    });
    if (breakdown.note) shares += '<div class="wq-muted" style="margin-top:8px">' + esc(breakdown.note) + '</div>';
    $('#appShares').html(shares);

    let table = '<table class="table table-striped"><thead><tr><th>{{ lang._("App") }}</th>'
              + '<th style="width:32%">{{ lang._("Share") }}</th><th>{{ lang._("Traffic") }}</th>'
              + '<th>{{ lang._("Percent") }}</th></tr></thead><tbody>';
    const top = rows[0].total || 1;
    rows.forEach((row, index) => {
        const rollup = row.name === 'Others';
        table += '<tr><td>' + (rollup ? '<i>' + esc(row.name) + '</i>'
                    : '<a href="#" class="wq-drill" data-drill="app" data-value=\'' + esc(row.name) + '\'><b>' + esc(row.name) + '</b></a>')
              +  '</td><td>' + shareBar(row.total / top, colors[index]) + '</td><td><b>' + gb(row.total)
              +  '</b></td><td>' + row.percent.toFixed(1) + '%</td></tr>';
    });
    $('#appTable').html(table + '</tbody></table>');
}
function showApp(name) {
    // An app is a set of domains. Show which domains carried it and which devices
    // used them, reusing the same drill targets as everywhere else.
    if (!name || name === 'Others') return;
    const consumer = (currentIntelligenceData && currentIntelligenceData.consumers) || {};
    const wanted = String(name).toLowerCase();
    const domains = (consumer.domains || []).filter(d => {
        const dn = String(d.domain || '').toLowerCase();
        return dn === wanted || dn.endsWith('.' + wanted) || wanted.indexOf(dn) >= 0;
    }).sort((a, b) => b.total - a.total);
    let html = drillHeader(name, '{{ lang._("domains carrying this app") }}',
        gb(domains.reduce((s, d) => s + d.total, 0)), domains.length + ' {{ lang._("domain(s)") }}');
    if (!domains.length) {
        return $('#appDrill').html(html + '<div class="alert alert-info">'
            + esc('This entry groups traffic by transport rather than by domain, so it has no domain list. Unnamed traffic cannot be attributed to specific sites.')
            + '</div>');
    }
    const top = domains[0].total || 1;
    html += '<table class="table table-condensed table-striped"><thead><tr><th>{{ lang._("Site") }}</th>'
         +  '<th style="width:30%">{{ lang._("Share") }}</th><th>{{ lang._("Traffic") }}</th></tr></thead><tbody>';
    for (const d of domains) {
        html += '<tr><td><a href="#" class="wq-drill" data-drill="domain" data-value=\'' + esc(d.domain) + '\'>'
             +  esc(d.domain) + '</a></td><td>' + shareBar(d.total / top, '#8b5cf6') + '</td><td><b>'
             +  gb(d.total) + '</b></td></tr>';
    }
    $('#appDrill').html(html + '</tbody></table>');
    document.getElementById('appDrill').scrollIntoView({behavior: 'smooth', block: 'start'});
}
let sessionPrevious = null, sessionTimer = null;
function rate(bytes, seconds) {
    if (!seconds || seconds <= 0 || bytes <= 0) return null;
    return bytes / seconds;
}
function rateText(value) {
    if (value === null) return '<span class="wq-muted">—</span>';
    const mbit = value * 8 / 1e6;
    return '<b>' + (mbit >= 1 ? mbit.toFixed(2) + ' Mbit/s' : (value / 1024).toFixed(0) + ' KB/s') + '</b>';
}
function deviceTable(data) {
    const rows = (data.devices || []).slice();
    if (!rows.length) return '<div class="alert alert-info">' + esc('No live WAN sessions from LAN devices right now.') + '</div>';
    // Rates come from the change since the previous poll: state counters are
    // cumulative, so a single reading cannot show a rate at all.
    const elapsed = sessionPrevious ? (data.collected_at - sessionPrevious.collected_at) : 0;
    const before = {};
    for (const row of (sessionPrevious && sessionPrevious.devices) || []) before[row.device] = row;
    rows.sort((a, b) => (b.download + b.upload) - (a.download + a.upload));
    const top = rows[0] ? (rows[0].download + rows[0].upload) || 1 : 1;
    let html = '<table class="table table-condensed table-striped"><thead><tr>'
             + '<th>{{ lang._("Device") }}</th><th style="width:20%">{{ lang._("Share of live traffic") }}</th>'
             + '<th>{{ lang._("Download") }}</th><th>{{ lang._("Upload") }}</th>'
             + '<th>{{ lang._("Down rate") }}</th><th>{{ lang._("Up rate") }}</th>'
             + '<th>{{ lang._("Sessions") }}</th></tr></thead><tbody>';
    for (const row of rows) {
        const prior = before[row.device];
        const down = prior ? rate(row.download - prior.download, elapsed) : null;
        const up = prior ? rate(row.upload - prior.upload, elapsed) : null;
        html += '<tr><td><a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(row.device) + '\'>'
             +  '<b>' + esc(row.name) + '</b></a><br><small class="wq-muted">' + esc(row.device) + '</small></td>'
             +  '<td>' + shareBar((row.download + row.upload) / top, '#3b82f6') + '</td>'
             +  '<td>' + gb(row.download) + '</td><td>' + gb(row.upload) + '</td>'
             +  '<td>' + rateText(down) + '</td><td>' + rateText(up) + '</td>'
             +  '<td>' + row.sessions + '</td></tr>';
    }
    return html + '</tbody></table>';
}

let currentSessionData = null;
function sessionTable(data) {
    const rows = (data && data.sessions) || [];
    if (!rows.length) return '<div class="alert alert-info">' + esc('No live WAN sessions from LAN devices right now.') + '</div>';
    let html = '<table class="table table-condensed table-striped"><thead><tr>'
             + '<th>{{ lang._("Device") }}</th><th>{{ lang._("Destination") }}</th>'
             + '<th>{{ lang._("Service") }}</th><th>{{ lang._("State") }}</th>'
             + '<th>{{ lang._("Age") }}</th><th>{{ lang._("Bytes") }}</th></tr></thead><tbody>';
    for (const row of rows) {
        const dest = row.remote_domain
            ? '<a href="#" class="wq-drill" data-drill="domain" data-value=\'' + esc(row.remote_domain) + '\'>' + esc(row.remote_domain) + '</a><br><small class="wq-muted">' + esc(row.remote) + '</small>'
            : esc(row.remote) + '<br><small class="wq-muted">' + esc('no DNS name observed') + '</small>';
        const mins = Math.floor(row.age_seconds / 60), secs = row.age_seconds % 60;
        html += '<tr data-filter="' + esc(((row.name || '') + ' ' + (row.remote_domain || '') + ' ' + row.remote + ' ' + row.service).toLowerCase()) + '">'
             +  '<td><a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(row.device) + '\'><b>' + esc(row.name) + '</b></a>'
             +  '<br><small class="wq-muted">' + esc(row.device) + (row.device_port ? ':' + row.device_port : '') + '</small></td>'
             +  '<td>' + dest + '</td><td>' + esc(row.service) + '</td>'
             +  '<td><small>' + esc(row.state) + '</small></td>'
             +  '<td>' + (mins ? mins + 'm ' : '') + secs + 's</td>'
             +  '<td><b>' + gb(row.bytes) + '</b></td></tr>';
    }
    return html + '</tbody></table>';
}
function renderSessions(data) {
    if (data.status !== 'ok') {
        $('#sessionTable').html('<div class="alert alert-danger">' + esc(data.error || 'Live sessions unavailable') + '</div>');
        return;
    }
    $('#sessionSummary').text(data.shown + ' of ' + data.total_states + ' states shown');
    $('#sessionDevices').html(deviceTable(data));
    $('#sessionTable').html(sessionTable(data));

    const elapsed = sessionPrevious ? (data.collected_at - sessionPrevious.collected_at) : 0;
    const before = {};
    for (const row of (sessionPrevious && sessionPrevious.devices) || []) before[row.device] = row;
    const ranked = (data.devices || []).slice()
        .sort((a, b) => (b.download + b.upload) - (a.download + a.upload)).slice(0, 10);
    const downRates = ranked.map(d => {
        const p = before[d.device];
        return p && elapsed > 0 ? Math.max(0, (d.download - p.download)) * 8 / elapsed / 1e6 : 0;
    });
    const upRates = ranked.map(d => {
        const p = before[d.device];
        return p && elapsed > 0 ? Math.max(0, (d.upload - p.upload)) * 8 / elapsed / 1e6 : 0;
    });
    makeChart('sessionChart', {
        type: 'bar',
        data: {labels: ranked.map(d => d.name), datasets: [
            {label: 'Download Mbit/s', data: downRates, backgroundColor: '#3b82f6'},
            {label: 'Upload Mbit/s', data: upRates, backgroundColor: '#06b6d4'}]},
        options: chartOptions(true)
    });
    sessionPrevious = data;
    currentSessionData = data;
    filterSessions();
}
function scheduleSessions() {
    if (sessionTimer) { clearInterval(sessionTimer); sessionTimer = null; }
    if (!$('#sessionAuto').is(':checked')) return;
    // Only poll while the tab is actually visible; a background timer hitting the
    // state table every few seconds for nobody is pure waste.
    sessionTimer = setInterval(function() {
        if ($('#sessions').hasClass('active')) refreshSessions();
    }, 5000);
}
function filterSessions() {
    const query = String($('#sessionSearch').val() || '').toLowerCase();
    $('#sessionTable tr[data-filter]').each(function() {
        $(this).toggle(!query || String($(this).data('filter')).includes(query));
    });
}
function refreshSessions() { ajaxCall('/api/wanquota/report/sessions', {}, renderSessions); }

let limitData = null;
/*
 * Services the catalogue does not know yet.
 *
 * Deliberately a proposal with its evidence rather than something applied: accepting a
 * candidate makes it shapeable, and shaping the wrong thing throttles traffic the
 * household needs. A candidate that cannot be capped says so before anyone accepts it,
 * because accepting it would produce a limit the planner then refuses.
 */
function renderDiscovered(data) {
    $('#rescanDiscovery').prop('disabled', false);
    const rows = (data.services || []).filter(item => item.status === 'new');
    if (data.status !== 'ok') {
        $('#discoveredServices').html('<div class="alert alert-danger">'
            + esc(data.error || 'Discovery data is unavailable') + '</div>');
        return;
    }
    if (!rows.length) {
        $('#discoveredServices').html('<div class="alert alert-info">'
            + esc('Nothing new. Every service moving real traffic is already known.')
            + '</div>');
        return;
    }
    let html = '<table class="table table-condensed table-striped"><thead><tr>'
             + '<th>{{ lang._("Service") }}</th><th>{{ lang._("Traffic") }}</th>'
             + '<th>{{ lang._("Evidence") }}</th><th>{{ lang._("Can be limited") }}</th>'
             + '<th></th></tr></thead><tbody>';
    for (const row of rows) {
        const named = row.named_from === 'known domain'
            ? '<span class="wq-pill wq-pill-ok">' + esc('recognised') + '</span>'
            : '<span class="wq-pill">' + esc('named after its domain') + '</span>';
        const belongs = row.belongs_to
            ? '<br><small class="wq-pill wq-pill-warn" title="'
              + esc('Most of its addresses already serve that service, so this is likely one of its delivery domains rather than a new service.')
              + '">' + esc('likely part of ' + row.belongs_to) + '</small>'
            : '';
        html += '<tr' + (row.infrastructure ? ' class="wq-limit-off"' : '') + '>'
             +  '<td><b>' + esc(row.label) + '</b>'
             +  (row.infrastructure ? ' <span class="wq-pill" title="'
                  + esc('A shared CDN, not a service anyone means to limit.') + '">'
                  + esc('infrastructure') + '</span>' : '')
             +  '<br><small class="wq-muted">' + esc(row.domain) + ' · ' + esc(row.category)
             +  '</small>' + belongs + '</td>'
             +  '<td>' + esc(bytesLabel(row.bytes_seen)) + '</td>'
             +  '<td>' + named + '<br><small class="wq-muted">'
             +  esc(row.hostname_count + ' hostname(s), ' + row.addresses + ' address(es)'
                    + (row.shared ? ', ' + row.shared + ' shared' : ''))
             +  '</small></td>'
             +  '<td>' + (row.cappable
                    ? '<span class="wq-pill wq-pill-ok">' + esc('yes') + '</span>'
                    : '<span class="wq-pill wq-pill-warn" title="'
                      + esc('Its addresses are shared with unrelated traffic, so a limit would be refused.')
                      + '">' + esc('no') + '</span>') + '</td>'
             +  '<td><button class="btn btn-xs btn-primary wq-accept" data-domain=\'' + esc(row.domain) + '\'>'
             +  esc('Accept') + '</button> '
             +  '<button class="btn btn-xs btn-default wq-ignore" data-domain=\'' + esc(row.domain) + '\'>'
             +  esc('Ignore') + '</button></td></tr>';
    }
    $('#discoveredServices').html(html + '</tbody></table>');
}
function refreshDiscovered(rescan) {
    if (rescan) {
        $('#rescanDiscovery').prop('disabled', true);
        $('#discoveredServices').html('<div class="alert alert-info">'
            + esc('Looking at what the network has been resolving…') + '</div>');
    }
    ajaxCall('/api/wanquota/limits/discovered', rescan ? {rescan: 1} : {}, renderDiscovered);
}
function decideService(domain, decision) {
    ajaxCall('/api/wanquota/limits/decide', {domain: domain, decision: decision},
        function(result) {
            if (result.status !== 'ok') {
                $('#limitStatus').html('<div class="alert alert-danger">'
                    + esc(result.error || 'The decision could not be recorded') + '</div>');
                return;
            }
            // An accepted service joins the catalogue, so the service list is rebuilt.
            refreshDiscovered(false);
            if (decision === 'accept') refreshLimits();
        });
}
/*
 * The effective state, in words, taken from the configuration rather than from the
 * checkboxes.
 *
 * A checkbox shows what the page last rendered; this shows what the firewall will
 * actually do. Those disagreed once — the tab only reloaded on its first visit, so a
 * change made in Settings left the switches contradicting the configuration — and
 * "am I live or in dry run?" is the one question here that must not be ambiguous.
 */
function renderLimitState(data) {
    if (!data.enabled) {
        $('#limitState').html('<span class="wq-pill">' + esc('limits off') + '</span>');
    } else if (data.dry_run) {
        $('#limitState').html('<span class="wq-pill wq-pill-warn" title="'
            + esc('Pipes and rules are recorded but nothing is shaped.') + '">'
            + esc('DRY RUN — nothing is being shaped') + '</span>');
    } else {
        $('#limitState').html('<span class="wq-pill wq-pill-ok">'
            + esc('live — limits are being enforced') + '</span>');
    }
}
function renderLimits(data) {
    limitData = data;
    $('#limitEnabled').prop('checked', !!data.enabled);
    $('#limitDryRun').prop('checked', !!data.dry_run);
    renderLimitState(data);
    const presets = Object.keys(data.resolutions || {});
    let html = '';
    for (const service of data.services || []) {
        // Each card states how well the service can actually be matched, because a
        // limit on a service with no observed addresses would do nothing at all.
        let badge;
        if (service.matched) {
            const shared = service.matched.shared_excluded;
            badge = '<span class="wq-pill wq-pill-ok">' + service.matched.addresses + ' '
                  + '{{ lang._("addresses") }}</span>'
                  + (shared ? ' <span class="wq-pill wq-pill-warn" title="'
                      + esc('Excluded because they are shared with other services; capping them would throttle unrelated traffic')
                      + '">' + shared + ' {{ lang._("shared, excluded") }}</span>' : '');
        } else if (service.refused) {
            badge = '<span class="wq-pill wq-pill-warn" title="' + esc(service.refused) + '">'
                  + '{{ lang._("nothing to match yet") }}</span>';
        } else {
            badge = '<span class="wq-pill">{{ lang._("not limited") }}</span>';
        }
        const options = ['<option value="">{{ lang._("Custom rate") }}</option>'].concat(
            presets.map(p => '<option value="' + esc(p) + '"' + (service.resolution === p ? ' selected' : '') + '>'
                + esc(p.toUpperCase().replace('_', ' ')) + ' — ' + data.resolutions[p] + ' Mbit/s</option>')
        ).join('');
        // Searchable on label, key and hostnames, so "netflix", "update" or a domain
        // all find the right card.
        const haystack = (service.label + ' ' + service.service + ' ' + (service.suffixes || []).join(' ')).toLowerCase();
        html += '<div class="wq-card wq-limit' + (service.selected ? '' : ' wq-limit-off') + '" data-service="' + esc(service.service) + '" data-search="' + esc(haystack) + '">'
             +  '<div class="wq-limit-head">'
             +  '<input type="checkbox" class="limit-on"' + (service.selected ? ' checked' : '') + '>'
             +  '<h3>' + esc(service.label) + '</h3>' + badge + '</div>'
             +  '<div class="wq-limit-row">'
             +  '<select class="form-control limit-res">' + options + '</select>'
             +  '<input class="form-control limit-mbit" type="number" step="0.1" min="0.1" placeholder="{{ lang._("Mbit/s") }}" value="' + esc(service.mbit) + '">'
             +  '</div>'
             +  '<div class="wq-muted">' + esc((service.suffixes || []).slice(0, 3).join(', ')) + '</div>'
             +  '</div>';
    }
    $('#limitCards').html(html || '<div class="alert alert-info">' + esc('No limitable services are available.') + '</div>');
    filterLimits();
}
function filterLimits() {
    const query = String($('#limitSearch').val() || '').toLowerCase().trim();
    let shown = 0;
    $('#limitCards .wq-limit').each(function() {
        // A selected service always stays visible: hiding a card whose switch is on
        // would make it look as though the limit had been removed.
        const selected = $(this).find('.limit-on').is(':checked');
        const match = !query || String($(this).data('search')).includes(query) || selected;
        $(this).toggle(match);
        if (match) shown++;
    });
    const total = $('#limitCards .wq-limit').length;
    $('#limitCount').text(query ? shown + ' / ' + total : total + ' {{ lang._("services") }}');
}
function collectLimits() {
    const limits = [];
    $('#limitCards .wq-limit').each(function() {
        if (!$(this).find('.limit-on').is(':checked')) return;
        limits.push({
            service: $(this).data('service'),
            resolution: $(this).find('.limit-res').val(),
            mbit: $(this).find('.limit-mbit').val(),
        });
    });
    return limits;
}
function saveLimits() {
    const payload = {
        enabled: $('#limitEnabled').is(':checked') ? 1 : 0,
        dry_run: $('#limitDryRun').is(':checked') ? 1 : 0,
        limits: collectLimits(),
    };
    $('#limitStatus').html('<div class="alert alert-info">' + esc('Applying…') + '</div>');
    $('#saveLimits').prop('disabled', true);
    ajaxCall('/api/wanquota/limits/set', payload, function(result) {
        $('#saveLimits').prop('disabled', false);
        if (result.status !== 'ok') {
            const problems = (result.errors || [result.error || 'Save failed']).map(esc).join('<br>');
            $('#limitStatus').html('<div class="alert alert-danger">' + problems + '</div>');
            return;
        }
        const mode = result.dry_run
            ? '{{ lang._("Saved. Dry run is on, so nothing is being shaped yet.") }}'
            : '{{ lang._("Saved and applied.") }}';
        $('#limitStatus').html('<div class="alert alert-success">' + esc(mode) + '</div>');
        refreshLimits();
        loadSettings();
        if (deviceLimitData) refreshDeviceLimits();
    });
}
/*
 * Reload the settings form from the model.
 *
 * Limits and Settings write the same fields — shaper_enabled and shaper_dry_run
 * among them — so whichever page did not make the change was showing a stale value
 * until the page was reloaded. Enabling limits and turning dry-run off from the
 * Limits page left Settings still showing them off, which reads as the save having
 * been lost. Every writer now refreshes the others.
 */
function loadSettings() {
    return mapDataToFormUI({'frm_wanquota_settings':'/api/wanquota/settings/get'})
        .done(function() { formatTokenizersUI(); $('.selectpicker').selectpicker('refresh'); });
}
/* Refresh whichever limits view has been opened, after a change made elsewhere. */
function refreshLimitViews() {
    if (limitData) refreshLimits();
    if (deviceLimitData) refreshDeviceLimits();
}
function refreshLimits() { ajaxCall('/api/wanquota/limits/get', {}, renderLimits); }

function renderExplain(data) {
    if (!data || data.status === 'failed' || !data.found) {
        $('#explainResult').html('<div class="alert alert-warning">'
            + esc((data && data.error) || 'That domain could not be identified.') + '</div>');
        return;
    }
    const service = data.service
        ? '<span class="wq-pill wq-pill-ok">' + esc(data.service.label) + '</span>'
        : '<span class="wq-pill">' + esc('No limitable service') + '</span>';
    const app = data.application
        ? '<span class="wq-pill">' + esc(data.application.name) + '</span>' : '';
    const shapeable = data.shapeable
        ? '<span class="wq-pill wq-pill-ok">' + esc('can be limited') + '</span>'
        : '<span class="wq-pill wq-pill-warn">' + esc('cannot be limited') + '</span>';
    let html = '<div class="wq-why"><h3>' + esc(data.domain) + '</h3>'
             + '<div class="wq-why-tags">' + service + app
             + '<span class="wq-pill">' + esc(data.category) + '</span>' + shapeable + '</div>'
             + '<div><b>' + gb(data.total) + '</b> ' + esc('attributed in this period') + '</div>';
    if ((data.devices || []).length) {
        html += '<div class="wq-muted" style="margin-top:6px">' + esc('Used by: ')
             +  data.devices.slice(0, 4).map(d =>
                    '<a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(d.device) + '\'>'
                    + esc(d.name) + '</a> (' + gb(d.total) + ')').join(', ')
             +  '</div>';
    }
    html += '<ol>' + (data.reasoning || []).map(r => '<li>' + esc(r) + '</li>').join('') + '</ol>';
    if (data.method) html += '<div class="wq-muted" style="margin-top:8px">' + esc(data.method) + '</div>';
    $('#explainResult').html(html + '</div>');
}
function explainDomain(domain) {
    if (!domain) return;
    $('#explainInput').val(domain);
    $('#explainResult').html('<div class="wq-muted">' + esc('Identifying…') + '</div>');
    ajaxCall('/api/wanquota/report/explain?domain=' + encodeURIComponent(domain), {}, renderExplain);
}

let wizardStep = 0;
const WIZARD_LAST = 5;
function showWizardStep(index) {
    wizardStep = Math.max(0, Math.min(WIZARD_LAST, index));
    $('.wq-step').each(function() {
        $(this).toggle(Number($(this).data('step')) === wizardStep);
    });
    $('#wizardSteps li').each(function() {
        const step = Number($(this).data('step'));
        $(this).toggleClass('active', step === wizardStep);
        // Steps already passed are marked done, so progress is visible at a glance.
        $(this).toggleClass('done', step < wizardStep);
    });
    $('#wizardBack').prop('disabled', wizardStep === 0);
    $('#wizardNext').prop('disabled', wizardStep === WIZARD_LAST);
}

let deviceLimitData = null;
function renderDeviceLimits(data) {
    deviceLimitData = data;
    $('#limitEnabled').prop('checked', !!data.enabled);
    $('#limitDryRun').prop('checked', !!data.dry_run);
    renderLimitState(data);
    /*
     * Say up front when this firewall cannot shape uploads. A capture engine using
     * netmap takes packets off the kernel path before ipfw sees them leaving a LAN
     * device, so an upload cap is accepted and then shapes nothing. Saying so here
     * is the difference between a known limitation and a silent failure.
     */
    const uploadOk = data.upload_supported !== false;
    if (uploadOk && data.upload_via_layer2) {
        /*
         * Uploads are shapeable here only through the experimental layer2 path. Say so
         * plainly: the rules are raw ipfw that a firewall or shaper reload removes
         * until the collector restores them, so a cap can lapse briefly.
         */
        $('#deviceLimitCapability').html('<div class="alert alert-warning">'
            + '<b>' + esc('Upload limits are using the experimental layer2 path.') + '</b><br>'
            + esc((data.interception || {}).engine + ' hides LAN egress from the normal '
                  + 'firewall hook, so upload caps are installed as raw ipfw rules outside '
                  + 'the traffic shaper. A firewall or shaper reload removes them until the '
                  + 'five-minute collector puts them back, so a cap can lapse briefly.')
            + '<br><small>' + esc('Use Verify to confirm the upload rule is matching.')
            + '</small></div>');
    } else if (uploadOk) {
        $('#deviceLimitCapability').empty();
    } else {
        const why = (data.interception || {}).reason || '';
        $('#deviceLimitCapability').html('<div class="alert alert-warning">'
            + '<b>' + esc('Upload limits are not available on this firewall.') + '</b><br>'
            + esc(why) + '<br><small>'
            + esc('Download limits work normally. Upload shaping is possible here through '
                  + 'an experimental layer2 path — enable it in Settings under Enforcement '
                  + 'if you want to try it. Use Verify below to see what each rule matched.')
            + '</small></div>');
    }
    const rows = data.devices || [];
    if (!rows.length) {
        $('#deviceLimitTable').html('<div class="alert alert-info">'
            + esc('No devices are currently visible on the LAN.') + '</div>');
        return;
    }
    let html = '<table class="table table-condensed table-striped"><thead><tr>'
             + '<th style="width:34px"></th><th>{{ lang._("Device") }}</th>'
             + '<th>{{ lang._("Matched on") }}</th>'
             + '<th>{{ lang._("Download Mbit/s") }}</th><th>{{ lang._("Upload Mbit/s") }}</th>'
             + '</tr></thead><tbody>';
    for (const row of rows) {
        // The MAC is offered as the key when there is one, because a limit keyed to
        // an address quietly stops applying the moment DHCP moves the device.
        const key = row.key || row.mac || row.address;
        const keyLabel = row.mac
            ? '<span class="wq-pill" title="' + esc('Survives a DHCP address change') + '">MAC</span>'
            : '<span class="wq-pill wq-pill-warn" title="' + esc('No MAC seen, so this limit is tied to the current address') + '">' + esc('address only') + '</span>';
        const search = (row.name + ' ' + row.address + ' ' + (row.mac || '') + ' ' + (row.hostname || '')).toLowerCase();
        html += '<tr data-device="' + esc(key) + '" data-search="' + esc(search) + '">'
             +  '<td><input type="checkbox" class="dev-on"' + (row.selected ? ' checked' : '') + '></td>'
             +  '<td><a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(row.address) + '\'>'
             +  '<b>' + esc(row.name) + '</b></a><br><small class="wq-muted">' + esc(row.address)
             +  (row.mac ? ' · ' + esc(row.mac) : '') + '</small>'
             +  (row.refused ? '<br><small class="wq-pill wq-pill-warn" title="' + esc(row.refused) + '">'
                    + esc('refused') + '</small>' : '')
             +  '</td><td>' + keyLabel + '</td>'
             +  '<td><input class="form-control dev-down" type="number" step="0.1" min="0.1" style="max-width:110px" value="' + esc(row.mbit) + '"></td>'
             +  '<td><input class="form-control dev-up" type="number" step="0.1" min="0.1" style="max-width:110px"'
             +  (uploadOk ? ' placeholder="{{ lang._("optional") }}"'
                          : ' disabled title="' + esc((data.interception || {}).reason || '') + '"'
                            + ' placeholder="{{ lang._("unavailable") }}"')
             /*
              * Keep showing a configured rate even when the field is disabled. Saving
              * reads disabled inputs too, so blanking it here would quietly delete a
              * rate the user set — and if they later remove the capture engine, the
              * limit they configured would be gone. Refusing to *apply* it is honest;
              * erasing what they configured is not.
              */
             +  ' value="' + esc(row.upload_mbit) + '">'
             +  (row.upload_refused
                    ? '<br><small class="wq-pill wq-pill-warn" title="' + esc(row.upload_refused) + '">'
                      + esc('not applied') + '</small>' : '')
             +  '</td>'
             +  '</tr>';
    }
    $('#deviceLimitTable').html(html + '</tbody></table>');
    filterDeviceLimits();
}
function filterDeviceLimits() {
    const query = String($('#deviceLimitSearch').val() || '').toLowerCase().trim();
    let shown = 0;
    $('#deviceLimitTable tbody tr').each(function() {
        const selected = $(this).find('.dev-on').is(':checked');
        const match = !query || String($(this).data('search')).includes(query) || selected;
        $(this).toggle(match);
        if (match) shown++;
    });
    const total = $('#deviceLimitTable tbody tr').length;
    $('#deviceLimitCount').text(query ? shown + ' / ' + total : total + ' {{ lang._("devices") }}');
}
function saveDeviceLimits() {
    const limits = [];
    $('#deviceLimitTable tbody tr').each(function() {
        if (!$(this).find('.dev-on').is(':checked')) return;
        limits.push({
            device: $(this).data('device'),
            mbit: $(this).find('.dev-down').val(),
            upload_mbit: $(this).find('.dev-up').val(),
        });
    });
    $('#deviceLimitStatus').html('<div class="alert alert-info">' + esc('Applying…') + '</div>');
    $('#saveDeviceLimits').prop('disabled', true);
    ajaxCall('/api/wanquota/limits/setDevices', {
        enabled: $('#limitEnabled').is(':checked') ? 1 : 0,
        dry_run: $('#limitDryRun').is(':checked') ? 1 : 0,
        limits: limits,
    }, function(result) {
        $('#saveDeviceLimits').prop('disabled', false);
        if (result.status !== 'ok') {
            $('#deviceLimitStatus').html('<div class="alert alert-danger">'
                + (result.errors || [result.error || 'Save failed']).map(esc).join('<br>') + '</div>');
            return;
        }
        $('#deviceLimitStatus').html('<div class="alert alert-success">' + esc(result.dry_run
            ? '{{ lang._("Saved. Dry run is on, so nothing is being shaped yet.") }}'
            : '{{ lang._("Saved and applied.") }}') + '</div>');
        refreshDeviceLimits();
        loadSettings();
    });
}
function refreshDeviceLimits() { ajaxCall('/api/wanquota/limits/devices', {}, renderDeviceLimits); }

/*
 * Show what the running rules have matched. A limit can be accepted, saved and
 * reported as applied while shaping nothing, and the byte counters are the only
 * direct evidence either way. Zero bytes on a rule whose traffic has been flowing
 * means that limit is not working.
 */
/* Bytes at whatever scale they actually are: 640 bytes is not "0.000 GB". */
function bytesLabel(bytes) {
    const value = Number(bytes) || 0;
    const units = [['GB', 1e9], ['MB', 1e6], ['kB', 1e3]];
    for (const [name, size] of units) {
        if (value >= size) return (value / size).toFixed(value / size < 10 ? 2 : 1) + ' ' + name;
    }
    return value + ' B';
}
function renderLimitVerify(data) {
    $('#verifyLimits').prop('disabled', false);
    if (data.status !== 'ok') {
        $('#limitVerify').html('<div class="alert alert-danger">'
            + esc(data.error || 'Could not read the running rules') + '</div>');
        return;
    }
    const rules = data.rules || [];
    if (!rules.length) {
        $('#limitVerify').html('<div class="alert alert-info">'
            + esc('No shaper rules are installed, so nothing is being limited.') + '</div>');
        return;
    }
    const kinds = {
        'service': '{{ lang._("service") }}',
        'device-download': '{{ lang._("download") }}',
        'device-upload': '{{ lang._("upload") }}',
    };
    /*
     * Applying reloads the shaper and resets every counter, so a zero straight after
     * a save means "no traffic yet", not "not working". Marking those rows as a
     * problem is how this table came to read as every limit being dead.
     */
    const settling = data.settling === true;
    let html = '';
    if (settling) {
        html += '<div class="alert alert-info">'
             + esc('Rules were installed ' + data.installed_seconds_ago
                   + ' seconds ago and the counters restart with them, so a rule showing '
                   + 'nothing here has simply had no traffic yet.') + '</div>';
    }
    html += '<div class="wq-table-wrap"><table class="table table-condensed table-striped">'
         +  '<thead><tr><th>{{ lang._("Limit") }}</th><th>{{ lang._("Kind") }}</th>'
         +  '<th>{{ lang._("Matches") }}</th><th>{{ lang._("Packets") }}</th>'
         +  '<th>{{ lang._("Matched") }}</th></tr></thead><tbody>';
    for (const rule of rules) {
        const idle = rule.bytes === 0;
        html += '<tr' + (idle && !settling ? ' class="danger"' : '') + '>'
             +  '<td><b>' + esc(rule.label || rule.pipe) + '</b>'
             +  '<br><small class="wq-muted">' + esc('pipe ' + rule.pipe) + '</small></td>'
             +  '<td>' + esc(kinds[rule.kind] || rule.kind) + '</td>'
             +  '<td><code>' + esc(rule.match) + '</code></td>'
             +  '<td>' + esc(rule.packets.toLocaleString()) + '</td>'
             +  '<td>' + (idle
                    ? '<span class="wq-pill' + (settling ? '' : ' wq-pill-warn') + '">'
                      + esc(settling ? 'nothing yet' : 'nothing') + '</span>'
                    : esc(bytesLabel(rule.bytes))) + '</td></tr>';
    }
    html += '</tbody></table></div><p class="wq-muted">' + esc(data.note || '') + '</p>';
    $('#limitVerify').html(html);
}
function verifyLimits() {
    $('#verifyLimits').prop('disabled', true);
    $('#limitVerify').html('<div class="alert alert-info">' + esc('Reading rules…') + '</div>');
    ajaxCall('/api/wanquota/limits/verify', {}, renderLimitVerify);
}

function renderIntelligence(data){currentIntelligenceData=data;if(/^#[0-9a-f]{6}$/i.test(data?.settings?.accent||''))document.querySelector('.wq-shell').style.setProperty('--wq-blue',data.settings.accent);$('#intelligenceCards').html(intelligenceCards(data));renderApps(data);$('#intelligenceDetails').html(intelligenceDetails(data));const groups=data.groups||[],categories=data.categories||[],providers=data?.summary?.providers||[],archives=data.archives||[];$('#overrideProvider').html(providers.map(x=>`<option value="${esc(x.name)}">${esc(x.name)}</option>`).join(''));makeChart('groupChart',{type:'bar',data:{labels:groups.map(x=>x.name),datasets:[{label:'Usage GB',data:groups.map(x=>x.total/1e9),backgroundColor:data?.settings?.accent||'#3b82f6'},{label:'Budget GB',data:groups.map(x=>x.budget?x.budget/1e9:null),backgroundColor:'rgba(128,128,128,.28)'}]},options:chartOptions(true)});renderCategoryBreakdown(data);const qualityOptions=chartOptions(false);qualityOptions.scales.y1={beginAtZero:true,position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'Cycle usage GB'}};makeChart('qualityChart',{type:'bar',data:{labels:providers.map(x=>x.name),datasets:[{label:'Latency ms',data:providers.map(x=>x.quality?.latency||0),backgroundColor:'#06b6d4'},{label:'Loss %',data:providers.map(x=>x.quality?.loss||0),backgroundColor:'#ef4444'},{type:'line',label:'Cycle usage GB',data:providers.map(x=>x.used/1e9),borderColor:'#8b5cf6',backgroundColor:'#8b5cf6',yAxisID:'y1',tension:.25}]},options:qualityOptions});makeChart('cycleChart',{type:'bar',data:{labels:archives.map(x=>x.provider+' '+x.start).slice(0,12),datasets:[{label:'Used GB',data:archives.map(x=>x.used/1e9).slice(0,12),backgroundColor:'#8b5cf6'},{label:'Unused GB',data:archives.map(x=>Math.max(0,x.quota-x.used)/1e9).slice(0,12),backgroundColor:'rgba(128,128,128,.25)'}]},options:chartOptions(false)});filterIntelligence();}
function refreshIntelligence(){const period=$('#intelligencePeriod').val();ajaxCall('/api/wanquota/report/intelligence_'+period,{},renderIntelligence);}
function filterIntelligence(){const query=String($('#intelligenceSearch').val()||'').toLowerCase();$('#intelligence [data-filter]').each(function(){$(this).toggle(!query||String($(this).data('filter')).includes(query));});}
function wanTable(providers) {
    if (!providers || !providers.length) return '<div class="alert alert-info">No per-WAN download data is available.</div>';
    let html = '<table class="table table-striped"><thead><tr><th>{{ lang._('Provider') }}</th><th>{{ lang._('Attributed flow total') }}</th><th>{{ lang._('Top devices') }}</th><th>{{ lang._('Top domains') }}</th><th>{{ lang._('Direction split') }}</th></tr></thead><tbody>';
    for (const provider of providers) {
        const devices = (provider.devices || []).slice(0, 5).map(item => `<a href="#" class="wq-drill" data-drill="device" data-value='${esc(item.ip)}'>${esc(item.name)}</a> (${gb(item.total)})`).join('<br>') || '—';
        const domains = (provider.domains || []).slice(0, 5).map(item => `<a href="#" class="wq-drill" data-drill="domain" data-value='${esc(item.domain)}'>${esc(item.domain)}</a> (${gb(item.total)})`).join('<br>') || '—';
        html += `<tr><td><a href="#" class="wq-drill" data-drill="provider" data-value='${esc(provider.name)}' title="Rank every device on this WAN"><b>${esc(provider.name)}</b></a><br><small>${esc(provider.logical_interface)} → ${esc(provider.interface)}</small></td><td><b>${gb(provider.total)}</b></td><td>${devices}</td><td>${domains}</td><td><span class="text-muted">Not attributable</span><br><small>${esc(provider.direction_attribution)}</small></td></tr>`;
    }
    return html + '</tbody></table>';
}
function matrixTable(rows) {
    if (!rows || !rows.length) return '<div class="alert alert-info">No attributed device/domain flows match this selection.</div>';
    let html = '<table class="table table-striped"><thead><tr><th>{{ lang._('Device') }}</th><th>{{ lang._('Domain') }}</th><th>{{ lang._('Attributed total') }}</th></tr></thead><tbody>';
    for (const row of rows.slice(0, 100)) html += `<tr><td><b>${esc(row.name)}</b><br><small>${esc(row.device)}</small></td><td>${esc(row.domain)}</td><td><b>${gb(row.total)}</b></td></tr>`;
    return html + '</tbody></table>';
}
function shareBar(fraction, color) {
    const pct = Math.max(0, Math.min(100, fraction * 100));
    return `<div class="wq-share"><span style="width:${pct.toFixed(1)}%;background:${color}"></span></div>`;
}
function drillHeader(title, subtitle, metric, note) {
    return `<div class="wq-drill-head"><div><div class="wq-muted">${esc(subtitle)}</div><h3 style="margin:2px 0">${esc(title)}</h3></div><div class="wq-drill-metric"><div class="wq-metric">${metric}</div><div class="wq-muted">${note}</div></div></div>`;
}
function providerBreakdown(kind, value) {
    const providers = (currentConsumerData || {}).providers || [];
    const found = [];
    for (const provider of providers) {
        const list = kind === 'device' ? (provider.devices || []) : (provider.domains || []);
        const hit = list.find(row => (kind === 'device' ? row.ip : row.domain) === value);
        if (hit) found.push({name: provider.name, interface: provider.interface, total: hit.total});
    }
    if (!found.length) return '';
    const cells = found.map(item => `<b>${esc(item.name)}</b> ${gb(item.total)} <small class="wq-muted">(${esc(item.interface)})</small>`).join(' · ');
    return `<div class="wq-muted" style="margin-bottom:10px">Seen on: ${cells}</div>`;
}
function devicePanel(deviceIp) {
    const data = currentConsumerData || {};
    const rows = (data.device_domains || []).filter(row => row.device === deviceIp)
        .sort((a, b) => b.total - a.total);
    const attribution = (data.device_attribution || []).find(item => item.device === deviceIp);
    const host = (data.hosts || []).find(item => item.ip === deviceIp);
    const viaProvider = (data.providers || []).flatMap(p => p.devices || []).find(row => row.ip === deviceIp);
    const label = (rows[0] && rows[0].name) || (host && host.name) || (viaProvider && viaProvider.name) || deviceIp;
    const external = attribution ? attribution.external : rows.reduce((sum, r) => sum + r.total, 0);
    const covered = attribution ? attribution.attributed : rows.reduce((sum, r) => sum + r.total, 0);
    const pct = attribution ? Number(attribution.coverage_percent || 0) : 0;
    let html = drillHeader(label, deviceIp + ' · sites this device used',
        gb(external), 'external traffic seen in flows');
    if (host) {
        html += `<div class="wq-muted" style="margin-bottom:8px">Device total from ntopng: <b>${gb(host.total)}</b> (${gb(host.download)} down · ${gb(host.upload)} up). That counts all traffic; the sites below are attributed from external flows only.</div>`;
    }
    html += providerBreakdown('device', deviceIp);
    if (attribution && attribution.likely_unattributable) {
        html += `<div class="alert alert-warning" style="margin-bottom:10px"><b>${esc(label)} moved ${gb(attribution.external)} that mostly cannot be resolved to a site</b> (${pct.toFixed(1)}% attributed).<br><small>That pattern is what encrypted DNS (DoH/DoT), a VPN tunnel, or ECH looks like from the firewall. The traffic is real and counted against your quota; only the destination names are hidden.</small></div>`;
    }
    if (!rows.length) {
        return html + '<div class="alert alert-info">No site could be attributed to this device for this period. Its traffic may be encrypted DNS, a VPN, or addresses with no recent DNS answer.</div>';
    }
    const top = rows[0].total || 1;
    html += '<table class="table table-striped"><thead><tr><th>{{ lang._('Site') }}</th><th style="width:32%">{{ lang._('Share of attributed') }}</th><th>{{ lang._('Traffic') }}</th></tr></thead><tbody>';
    for (const row of rows) {
        html += `<tr><td><a href="#" class="wq-drill" data-drill="domain" data-value='${esc(row.domain)}'>${esc(row.domain)}</a></td><td>${shareBar(row.total / top, '#8b5cf6')}</td><td><b>${gb(row.total)}</b></td></tr>`;
    }
    if (attribution && attribution.unattributed > 0) {
        html += `<tr class="wq-unattributed"><td><i>Unattributed</i></td><td>${shareBar(attribution.unattributed / top, 'rgba(128,128,128,.45)')}</td><td><b>${gb(attribution.unattributed)}</b></td></tr>`;
    }
    html += '</tbody></table>';
    html += `<div class="wq-muted"><b>${gb(covered)}</b> of <b>${gb(external)}</b> external traffic attributed (${pct.toFixed(1)}%). Encrypted DNS, VPNs, ECH, and shared CDN addresses stay unattributed.</div>`;
    return html;
}
function domainPanel(domain) {
    const data = currentConsumerData || {};
    const rows = (data.device_domains || []).filter(row => row.domain === domain)
        .sort((a, b) => b.total - a.total);
    const summary = (data.domains || []).find(item => item.domain === domain);
    const total = rows.reduce((sum, r) => sum + r.total, 0);
    let html = drillHeader(domain, 'devices that used this site', gb(summary ? summary.total : total),
        summary ? `${summary.ip_count} observed IP(s)` : 'attributed traffic');
    html += providerBreakdown('domain', domain);
    if (!rows.length) {
        return html + '<div class="alert alert-info">No LAN device could be attributed to this site for this period. It may only appear in per-WAN download flows, where the internal address is not retained.</div>';
    }
    const top = rows[0].total || 1;
    html += '<table class="table table-striped"><thead><tr><th>{{ lang._('Device') }}</th><th style="width:32%">{{ lang._('Share') }}</th><th>{{ lang._('Traffic') }}</th></tr></thead><tbody>';
    for (const row of rows) {
        html += `<tr><td><a href="#" class="wq-drill" data-drill="device" data-value='${esc(row.device)}'><b>${esc(row.name)}</b></a><br><small>${esc(row.device)}</small></td><td>${shareBar(row.total / top, '#3b82f6')}</td><td><b>${gb(row.total)}</b></td></tr>`;
    }
    return html + '</tbody></table>';
}
function refreshMatrix() {
    if (!currentConsumerData) return;
    const device = $('#drillDevice').val(), domain = $('#drillDomain').val();
    $('#drillClear').toggle(Boolean(device || domain));
    if (device && !domain) { $('#deviceDomainMatrix').html(devicePanel(device)); return; }
    if (domain && !device) { $('#deviceDomainMatrix').html(domainPanel(domain)); return; }
    const rows = (currentConsumerData.device_domains || []).filter(row => (!device || row.device === device) && (!domain || row.domain === domain));
    $('#deviceDomainMatrix').html(matrixTable(rows));
}
/*
 * Every device on one WAN, ranked.
 *
 * The per-WAN table shows a provider's five busiest devices in a single cell, which
 * answers "who is on this gateway" only if the answer is short. This ranks all of
 * them with their share, so the question "which device is eating this gateway" has a
 * real answer. The data is already in the consumers report, so opening this costs
 * nothing.
 */
/*
 * A WAN name is clickable from the Summary and Intelligence cards as well as the
 * per-WAN table, but the ranking lives on the Consumers tab and is built from the
 * consumers report. Opening from elsewhere therefore switches tab and, if that
 * report has not been fetched yet, fetches it before drilling — otherwise the panel
 * would report "no attributed traffic" purely because nothing had loaded.
 */
function openProvider(name) {
    $('a[href="#consumers"]').tab('show');
    if (currentConsumerData) { providerDrill(name); return; }
    ajaxCall('/api/wanquota/report/consumers_' + $('#consumerPeriod').val(), {}, function(data) {
        currentConsumerData = data;
        providerDrill(name);
    });
}
function providerDrill(name) {
    const provider = (currentConsumerData?.providers || [])
        .find(item => String(item.name) === String(name));
    if (!provider) {
        $('#providerDrill').html('<div class="alert alert-info">'
            + esc('No attributed traffic is recorded for that WAN in this period.') + '</div>');
        return;
    }
    const devices = (provider.devices || []).slice();
    devices.sort((a, b) => (b.total || 0) - (a.total || 0));
    const attributed = devices.reduce((sum, item) => sum + (item.total || 0), 0);
    let html = '<h3>' + esc(provider.name) + ' — ' + esc('devices by attributed traffic')
             + ' <a href="#" class="wq-drill wq-muted" data-drill="provider-close" data-value="">'
             + esc('hide') + '</a></h3>'
             + '<div class="wq-muted" style="margin-bottom:8px">'
             + esc(provider.logical_interface + ' → ' + provider.interface
                   + ' · ' + gb(provider.total) + ' attributed in this period') + '</div>';
    if (!devices.length) {
        $('#providerDrill').html(html + '<div class="alert alert-info">'
            + esc('No device on this WAN has attributable flow data.') + '</div>');
        return;
    }
    html += '<table class="table table-condensed table-striped"><thead><tr>'
         +  '<th>#</th><th>{{ lang._("Device") }}</th><th>{{ lang._("Attributed") }}</th>'
         +  '<th>{{ lang._("Share of this WAN") }}</th></tr></thead><tbody>';
    devices.forEach(function(item, index) {
        const share = attributed ? (item.total || 0) / attributed * 100 : 0;
        html += '<tr><td>' + (index + 1) + '</td>'
             +  '<td><a href="#" class="wq-drill" data-drill="device" data-value=\'' + esc(item.ip) + '\'>'
             +  '<b>' + esc(item.name || item.ip) + '</b></a>'
             +  '<br><small class="wq-muted">' + esc(item.ip) + '</small></td>'
             +  '<td><b>' + esc(gb(item.total)) + '</b></td>'
             +  '<td>' + shareBar(share / 100, '#1677a8') + '<small>' + share.toFixed(1) + '%</small></td>'
             +  '</tr>';
    });
    html += '</tbody></table><p class="wq-muted">'
         +  esc('Ranking uses attributed flow totals, so a device using encrypted DNS or a '
               + 'VPN may be under-represented. Direction splits are not available per WAN.')
         +  '</p>';
    $('#providerDrill').html(html);
    document.getElementById('providerDrill').scrollIntoView({behavior: 'smooth', block: 'center'});
}
function drillTo(kind, value) {
    if (kind === 'provider') { openProvider(value); return; }
    if (kind === 'provider-close') { $('#providerDrill').empty(); return; }
    const target = kind === 'device' ? '#drillDevice' : '#drillDomain';
    const other = kind === 'device' ? '#drillDomain' : '#drillDevice';
    if (!$(target + " option[value='" + String(value).replace(/'/g, "\\'") + "']").length) return;
    $(other).val('');
    $(target).val(value);
    refreshMatrix();
    document.getElementById('deviceDomainMatrix').scrollIntoView({behavior: 'smooth', block: 'center'});
}
function healthTable(data) {
    if (!data || !data.checks) return '<div class="alert alert-danger">Health report unavailable</div>';
    const version = data.plugin_version ? '<div class="wq-muted" style="margin-bottom:10px">os-wanquota ' + esc(data.plugin_version) + '</div>' : '';
    const labels = {ok: 'success', stale: 'warning', failed: 'danger', disabled: 'default'};
    const color = data.status === 'ok' ? '#10b981' : data.status === 'failed' ? '#ef4444' : '#f59e0b';
    // Version belongs where an operator looks when something is wrong.
    let html = `<div class="wq-hero" style="background:linear-gradient(135deg,#172033,${color})"><h2><span class="wq-health-dot" style="background:${color};box-shadow:0 0 12px ${color}"></span>Data health: ${esc(data.status).toUpperCase()}</h2><p>All reporting depends on fresh accounting sources · ${esc(data.generated_at)}</p></div><div class="wq-grid">`;
    for (const item of data.checks) { const c=item.status==='ok'?'#10b981':item.status==='failed'?'#ef4444':'#f59e0b'; html+=`<div class="wq-card"><h3><span class="wq-health-dot" style="background:${c}"></span>${esc(item.name)}</h3><div class="wq-metric" style="font-size:18px">${esc(item.status).toUpperCase()}</div><div class="wq-muted">${esc(item.detail)}</div></div>`; }
    html += '</div>';
    html = version + html;
    html += '<table class="table table-striped"><thead><tr><th>{{ lang._('Source') }}</th><th>{{ lang._('Status') }}</th><th>{{ lang._('Detail') }}</th><th>{{ lang._('Freshness') }}</th></tr></thead><tbody>';
    for (const item of data.checks) {
        const freshness = item.age_seconds == null ? '—' : item.age_seconds < 120 ? item.age_seconds + ' seconds' : Math.round(item.age_seconds / 60) + ' minutes';
        html += `<tr><td><b>${esc(item.name)}</b></td><td><span class="label label-${labels[item.status] || 'default'}">${esc(item.status)}</span></td><td>${esc(item.detail)}</td><td>${freshness}</td></tr>`;
    }
    return html + '</tbody></table>';
}
function refreshConsumers() {
    const period = $('#consumerPeriod').val();
    ajaxCall('/api/wanquota/report/consumers_' + period, {}, function(data) {
        currentConsumerData = data;
        renderConsumerCharts(data);
        $('#hostConsumers').html(consumerTable(data.hosts, 'name'));
        $('#domainConsumers').html(consumerTable(data.domains, 'domain'));
        const coverage = Number(data?.domain_attribution?.coverage_percent || 0).toFixed(1);
        $('#domainCoverage').html(`<div class="alert alert-info"><b>Domain attribution coverage: ${coverage}%</b><br><small>${esc(data?.domain_attribution?.method || '')}. Encrypted DNS, VPNs, ECH, shared CDN IPs, and uncached answers can remain unattributed.</small></div>`);
        $('#wanConsumers').html(wanTable(data.providers));
        // Union with the headline tables: a device with no attributed flow, or a
        // domain no longer in the capped matrix, is still clickable there and must
        // resolve to a panel rather than silently doing nothing.
        const deviceMap = new Map((data.hosts || []).map(row => [row.ip, row.name]));
        for (const row of data.device_domains || []) deviceMap.set(row.device, row.name);
        // Per-WAN rows come from provider-scope flows, which can name devices and
        // domains the LAN-scope matrix never saw. They are clickable too, so they
        // must resolve.
        for (const provider of data.providers || []) {
            for (const row of provider.devices || []) if (!deviceMap.has(row.ip)) deviceMap.set(row.ip, row.name);
        }
        const devices = [...deviceMap.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
        const domains = [...new Set([
            ...(data.domains || []).map(row => row.domain),
            ...(data.device_domains || []).map(row => row.domain),
            ...(data.providers || []).flatMap(provider => (provider.domains || []).map(row => row.domain)),
        ])].sort();
        $('#drillDevice').html('<option value="">All devices</option>' + devices.map(item => `<option value="${esc(item[0])}">${esc(item[1])}</option>`).join(''));
        $('#drillDomain').html('<option value="">All domains</option>' + domains.map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join(''));
        refreshMatrix();
    });
}
function refreshReports() {
    ajaxCall('/api/wanquota/report/summary', {}, function(data) { currentSummaryData = data; $('#summaryReport').html(summaryTable(data)); renderSummaryCharts(data); });
    ajaxCall('/api/wanquota/report/daily', {}, function(data) { $('#dailyReport').html(historyTable(data)); renderHistoryChart('dailyChart',data); });
    ajaxCall('/api/wanquota/report/monthly', {}, function(data) { $('#monthlyReport').html(historyTable(data)); renderHistoryChart('monthlyChart',data); });
    ajaxCall('/api/wanquota/report/health', {}, function(data) { $('#healthReport').html(healthTable(data)); });
}
$(document).ready(function() {
    loadSettings();
    refreshReports();
    refreshConsumers();
    refreshIntelligence();
    if (window.location.hash) {
        const tab = $('a[href="' + window.location.hash + '"]');
        if (tab.length) tab.tab('show');
    }
    $('#maintabs a').on('shown.bs.tab', function(event) {
        history.replaceState(null, '', event.target.hash);
        const pane = $(event.target.hash);
        pane.find('canvas').each(function() { if (wqCharts[this.id]) wqCharts[this.id].resize(); });
    });
    $('#refreshConsumers,#consumerPeriod').on('click change', refreshConsumers);
    // Delegated: the consumer tables and drill panels are re-rendered on every
    // refresh, so per-element handlers would be lost.
    $('#consumers').on('click', 'a.wq-drill', function(event) {
        event.preventDefault();
        drillTo($(this).data('drill'), $(this).data('value'));
    });
    showWizardStep(0);
    $('#wizardNext').on('click', function() { showWizardStep(wizardStep + 1); });
    $('#wizardBack').on('click', function() { showWizardStep(wizardStep - 1); });
    $('#wizardSteps').on('click', 'li', function() { showWizardStep(Number($(this).data('step'))); });
    $('#limitSearch').on('keyup', filterLimits);
    $('#deviceLimitSearch').on('keyup', filterDeviceLimits);
    $('#saveDeviceLimits').on('click', saveDeviceLimits);
    $('#verifyLimits').on('click', verifyLimits);
    $('#rescanDiscovery').on('click', function() { refreshDiscovered(true); });
    $('#discoveredServices').on('click', '.wq-accept', function() {
        decideService($(this).data('domain'), 'accept');
    });
    $('#discoveredServices').on('click', '.wq-ignore', function() {
        decideService($(this).data('domain'), 'ignore');
    });
    $('a[href="#limitsService"]').on('shown.bs.tab', function() { refreshDiscovered(false); });
    startThroughput();
    $('a[href="#summary"]').on('shown.bs.tab', startThroughput);
    $('a[data-toggle="tab"]').not('a[href="#summary"]').on('shown.bs.tab', stopThroughput);
    // Summary has no drill handler of its own; Intelligence already routes through
    // drillTo, so binding it here too would run the drill twice.
    $('#summary').on('click', 'a.wq-drill[data-drill="provider"]', function(event) {
        event.preventDefault();
        openProvider($(this).data('value'));
    });
    /*
     * Reload on tab entry as well as after a save. A change can also arrive from
     * outside this page — the MCP server can set limits and settings — so the form
     * is refreshed when it is opened rather than trusted to be current.
     */
    $('a[href="#settings"]').on('shown.bs.tab', loadSettings);
    $('a[href="#limitsService"]').on('shown.bs.tab', refreshLimits);
    $('#deviceLimitTable').on('change', '.dev-on', filterDeviceLimits);
    $('a[href="#limitsDevice"]').on('shown.bs.tab', function() {
        if (!deviceLimitData) refreshDeviceLimits();
    });
    $('#explainGo').on('click', function() { explainDomain($('#explainInput').val().trim()); });
    $('#explainInput').on('keydown', function(event) {
        if (event.key === 'Enter') explainDomain($(this).val().trim());
    });
    $('#saveLimits').on('click', saveLimits);
    // Toggling a card dims it immediately so the effect of the switch is visible
    // before saving.
    $('#limitCards').on('change', '.limit-on', function() {
        $(this).closest('.wq-limit').toggleClass('wq-limit-off', !$(this).is(':checked'));
    });
    // A preset and a custom rate are mutually exclusive; picking one clears the other.
    $('#limitCards').on('change', '.limit-res', function() {
        if ($(this).val()) $(this).closest('.wq-limit').find('.limit-mbit').val('');
    });
    $('#limitCards').on('input', '.limit-mbit', function() {
        if ($(this).val()) $(this).closest('.wq-limit').find('.limit-res').val('');
    });
    /*
     * Always refresh, not only on the first visit. This previously reloaded only when
     * nothing had been loaded yet, which left the shared enable and dry-run switches
     * showing whatever they showed the first time the tab was opened — so changing
     * them in Settings left Limits contradicting the configuration, and the state a
     * user read here could be stale in either direction.
     */
    $('#maintabs a[href="#limits"]').on('shown.bs.tab', function() {
        refreshLimits();
        refreshDiscovered(false);
    });
    $('#refreshSessions').on('click', refreshSessions);
    $('#sessionSearch').on('keyup', filterSessions);
    $('#apps,#sessions').on('click', 'a.wq-drill', function(event) {
        event.preventDefault();
        const kind = $(this).data('drill'), value = $(this).data('value');
        if (kind === 'app') { showApp(value); return; }
        if (kind === 'explain') { $('a[href="#apps"]').tab('show'); explainDomain(value); return; }
        $('a[href="#consumers"]').tab('show');
        drillTo(kind, value);
    });
    $('#maintabs a[href="#sessions"]').on('shown.bs.tab', function() {
        refreshSessions();
        scheduleSessions();
    });
    $('#sessionAuto').on('change', scheduleSessions);
    $('#intelligence').on('click', 'a.wq-drill', function(event) {
        event.preventDefault();
        const kind = $(this).data('drill'), value = $(this).data('value');
        if (kind === 'category') { showCategory(value); return; }
        if (kind === 'explain') { $('a[href="#apps"]').tab('show'); explainDomain(value); return; }
        // device and domain live on the Consumers tab; show it, then drill there.
        $('a[href="#consumers"]').tab('show');
        drillTo(kind, value);
    });
    $('#intelligence').on('click', '#categoryClear', function() { $('#categoryDrill').empty(); });
    $('#drillClear').on('click', function() {
        $('#drillDevice').val('');
        $('#drillDomain').val('');
        refreshMatrix();
    });
    $('#drillDevice,#drillDomain').on('change', refreshMatrix);
    $('#refreshIntelligence,#intelligencePeriod').on('click change', refreshIntelligence);
    $('#intelligenceSearch').on('input', filterIntelligence);
    $('#applyOverride').on('click',function(){const button=$(this),payload={provider:$('#overrideProvider').val(),mode:$('#overrideMode').val(),hours:$('#overrideHours').val()};button.prop('disabled',true);$('#overrideStatus').text('Applying…');ajaxCall('/api/wanquota/override',payload,function(result){button.prop('disabled',false);$('#overrideStatus').text(result.status==='ok'?'Override saved until '+new Date(result.expires*1000).toLocaleString():(result.error||'Override failed'));refreshIntelligence();});});
    $('#unitToggle').on('click',function(){wqUnit=wqUnit==='GB'?'MB':'GB';$(this).text(wqUnit);refreshReports();refreshConsumers();if(currentIntelligenceData)renderIntelligence(currentIntelligenceData);});
    $('#contrastToggle').on('click',function(){$('.wq-shell').toggleClass('wq-contrast');});
    $('#wallboardToggle').on('click',function(){$('body').toggleClass('wq-wallboard');if($('body').hasClass('wq-wallboard'))$('a[href="#intelligence"]').tab('show');Object.values(wqCharts).forEach(c=>c.resize());});
    $('#exportSummaryCsv').on('click', function() {
        if (!currentSummaryData) return;
        const rows = (currentSummaryData.providers || []).map(p => [p.name, p.logical_interface, p.interface, p.start, p.end, p.rx, p.tx, p.used, p.quota, p.remaining, p.percent, p.daily_budget, p.projected]);
        downloadReport('wan-quota-summary.csv', csvDocument(['provider','logical_interface','interface','cycle_start','cycle_end','download_bytes','upload_bytes','used_bytes','quota_bytes','remaining_bytes','percent','daily_budget_bytes','projected_bytes'], rows), 'text/csv;charset=utf-8');
    });
    $('#exportSummaryJson').on('click', function() { if (currentSummaryData) downloadReport('wan-quota-summary.json', JSON.stringify(currentSummaryData, null, 2), 'application/json'); });
    $('#exportConsumersCsv').on('click', function() {
        if (!currentConsumerData) return;
        const rows = (currentConsumerData.device_domains || []).map(r => [currentConsumerData.period, r.device, r.name, r.domain, r.total]);
        downloadReport('wan-consumers-' + currentConsumerData.period + '.csv', csvDocument(['period','device_ip','device_name','domain','attributed_bytes'], rows), 'text/csv;charset=utf-8');
    });
    $('#exportConsumersJson').on('click', function() { if (currentConsumerData) downloadReport('wan-consumers-' + currentConsumerData.period + '.json', JSON.stringify(currentConsumerData, null, 2), 'application/json'); });
    $('#saveAct').click(function() {
        $('#saveAct_progress').addClass('fa fa-spinner fa-pulse');
        saveFormToEndpoint('/api/wanquota/settings/set', 'frm_wanquota_settings', function() {
            $('#saveAct_progress').removeClass('fa fa-spinner fa-pulse');
            refreshReports();
            refreshLimitViews();
        });
    });
});
</script>
