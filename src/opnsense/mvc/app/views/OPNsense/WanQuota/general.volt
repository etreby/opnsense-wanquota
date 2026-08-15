<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#summary">{{ lang._('Summary') }}</a></li>
    <li><a data-toggle="tab" href="#consumers">{{ lang._('Consumers') }}</a></li>
    <li><a data-toggle="tab" href="#daily">{{ lang._('Daily history') }}</a></li>
    <li><a data-toggle="tab" href="#monthly">{{ lang._('Monthly history') }}</a></li>
    <li><a data-toggle="tab" href="#health">{{ lang._('Data health') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>

<div class="tab-content content-box tab-content">
    <div id="summary" class="tab-pane fade in active"><div style="padding:16px"><div class="btn-group pull-right"><button id="exportSummaryCsv" class="btn btn-default" type="button"><i class="fa fa-download"></i> CSV</button><button id="exportSummaryJson" class="btn btn-default" type="button"><i class="fa fa-download"></i> JSON</button></div><div id="summaryReport"></div></div></div>
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
            <h3>{{ lang._('Top LAN consumers') }}</h3><div id="hostConsumers"></div>
            <h3>{{ lang._('Top attributed domains') }}</h3><div id="domainConsumers"></div>
            <div id="domainCoverage"></div>
            <h3>{{ lang._('Per-WAN attributed traffic') }}</h3><div id="wanConsumers"></div>
            <h3>{{ lang._('Device and domain drill-down') }}</h3>
            <div class="form-inline" style="margin-bottom:10px">
                <label for="drillDevice">{{ lang._('Device') }}:&nbsp;</label><select id="drillDevice" class="form-control"><option value="">All devices</option></select>
                <label for="drillDomain" style="margin-left:10px">{{ lang._('Domain') }}:&nbsp;</label><select id="drillDomain" class="form-control"><option value="">All domains</option></select>
            </div>
            <div id="deviceDomainMatrix"></div>
        </div>
    </div>
    <div id="daily" class="tab-pane fade"><div id="dailyReport" style="padding:16px"></div></div>
    <div id="monthly" class="tab-pane fade"><div id="monthlyReport" style="padding:16px"></div></div>
    <div id="health" class="tab-pane fade"><div id="healthReport" style="padding:16px"></div></div>
    <div id="settings" class="tab-pane fade">
        <div class="content-box" style="padding-bottom:1.5em">
            {{ partial("layout_partials/base_form", ['fields':generalForm,'id':'frm_wanquota_settings']) }}
            <div class="col-md-12"><hr><button class="btn btn-primary" id="saveAct" type="button"><b>{{ lang._('Save') }}</b> <i id="saveAct_progress"></i></button></div>
        </div>
    </div>
</div>

<script>
function gb(value) { return (Number(value || 0) / 1000000000).toFixed(3) + ' GB'; }
function esc(value) { return $('<div>').text(value ?? '').html(); }
function downloadReport(filename, content, type) {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([content], {type: type}));
    link.download = filename;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
function csvCell(value) { return '"' + String(value ?? '').replace(/"/g, '""') + '"'; }
function csvDocument(headers, rows) {
    return '\uFEFF' + [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n') + '\r\n';
}
function summaryTable(data) {
    if (!data || !data.providers) return '<div class="alert alert-danger">Report unavailable</div>';
    let html = '<table class="table table-striped"><thead><tr><th>Provider</th><th>Cycle</th><th>Download</th><th>Upload</th><th>Used</th><th>Remaining</th><th>Daily budget</th><th>Projected</th></tr></thead><tbody>';
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
        html += '<h3>' + esc(provider.name) + '</h3><table class="table table-condensed table-striped"><thead><tr><th>Date</th><th>Download</th><th>Upload</th><th>Total</th></tr></thead><tbody>';
        for (const row of provider.rows) html += `<tr><td>${row.date}</td><td>${gb(row.rx)}</td><td>${gb(row.tx)}</td><td>${gb(row.total)}</td></tr>`;
        html += '</tbody></table>';
    }
    return html;
}
function consumerTable(rows, key) {
    if (!rows || !rows.length) return '<div class="alert alert-info">No traffic data is available for this period.</div>';
    let html = key === 'name'
        ? '<table class="table table-striped"><thead><tr><th>Device</th><th>Download</th><th>Upload</th><th>Total</th></tr></thead><tbody>'
        : '<table class="table table-striped"><thead><tr><th>Attributed domain</th><th>Observed IPs</th><th>Attributed total</th></tr></thead><tbody>';
    for (const row of rows) {
        if (key === 'name') {
            html += `<tr><td><b>${esc(row.name)}</b><br><small>${esc(row.ip)}</small></td><td>${gb(row.download)}</td><td>${gb(row.upload)}</td><td><b>${gb(row.total)}</b></td></tr>`;
        } else {
            html += `<tr><td><b>${esc(row.domain)}</b></td><td>${row.ip_count}</td><td><b>${gb(row.total)}</b></td></tr>`;
        }
    }
    return html + '</tbody></table>';
}
let currentSummaryData = null, currentConsumerData = null;
function wanTable(providers) {
    if (!providers || !providers.length) return '<div class="alert alert-info">No per-WAN download data is available.</div>';
    let html = '<table class="table table-striped"><thead><tr><th>Provider</th><th>Attributed flow total</th><th>Top devices</th><th>Top domains</th><th>Direction split</th></tr></thead><tbody>';
    for (const provider of providers) {
        const devices = (provider.devices || []).slice(0, 5).map(item => `${esc(item.name)} (${gb(item.total)})`).join('<br>') || '—';
        const domains = (provider.domains || []).slice(0, 5).map(item => `${esc(item.domain)} (${gb(item.total)})`).join('<br>') || '—';
        html += `<tr><td><b>${esc(provider.name)}</b><br><small>${esc(provider.logical_interface)} → ${esc(provider.interface)}</small></td><td><b>${gb(provider.total)}</b></td><td>${devices}</td><td>${domains}</td><td><span class="text-muted">Not attributable</span><br><small>${esc(provider.direction_attribution)}</small></td></tr>`;
    }
    return html + '</tbody></table>';
}
function matrixTable(rows) {
    if (!rows || !rows.length) return '<div class="alert alert-info">No attributed device/domain flows match this selection.</div>';
    let html = '<table class="table table-striped"><thead><tr><th>Device</th><th>Domain</th><th>Attributed total</th></tr></thead><tbody>';
    for (const row of rows.slice(0, 100)) html += `<tr><td><b>${esc(row.name)}</b><br><small>${esc(row.device)}</small></td><td>${esc(row.domain)}</td><td><b>${gb(row.total)}</b></td></tr>`;
    return html + '</tbody></table>';
}
function refreshMatrix() {
    if (!currentConsumerData) return;
    const device = $('#drillDevice').val(), domain = $('#drillDomain').val();
    const rows = (currentConsumerData.device_domains || []).filter(row => (!device || row.device === device) && (!domain || row.domain === domain));
    $('#deviceDomainMatrix').html(matrixTable(rows));
}
function healthTable(data) {
    if (!data || !data.checks) return '<div class="alert alert-danger">Health report unavailable</div>';
    const labels = {ok: 'success', stale: 'warning', failed: 'danger', disabled: 'default'};
    let html = `<div class="alert alert-${data.status === 'ok' ? 'success' : data.status === 'failed' ? 'danger' : 'warning'}"><b>Overall data health: ${esc(data.status)}</b><br><small>Generated: ${esc(data.generated_at)}</small></div>`;
    html += '<table class="table table-striped"><thead><tr><th>Source</th><th>Status</th><th>Detail</th><th>Freshness</th></tr></thead><tbody>';
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
        $('#hostConsumers').html(consumerTable(data.hosts, 'name'));
        $('#domainConsumers').html(consumerTable(data.domains, 'domain'));
        const coverage = Number(data?.domain_attribution?.coverage_percent || 0).toFixed(1);
        $('#domainCoverage').html(`<div class="alert alert-info"><b>Domain attribution coverage: ${coverage}%</b><br><small>${esc(data?.domain_attribution?.method || '')}. Encrypted DNS, VPNs, ECH, shared CDN IPs, and uncached answers can remain unattributed.</small></div>`);
        $('#wanConsumers').html(wanTable(data.providers));
        const devices = [...new Map((data.device_domains || []).map(row => [row.device, row.name])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
        const domains = [...new Set((data.device_domains || []).map(row => row.domain))].sort();
        $('#drillDevice').html('<option value="">All devices</option>' + devices.map(item => `<option value="${esc(item[0])}">${esc(item[1])}</option>`).join(''));
        $('#drillDomain').html('<option value="">All domains</option>' + domains.map(item => `<option value="${esc(item)}">${esc(item)}</option>`).join(''));
        refreshMatrix();
    });
}
function refreshReports() {
    ajaxCall('/api/wanquota/report/summary', {}, function(data) { currentSummaryData = data; $('#summaryReport').html(summaryTable(data)); });
    ajaxCall('/api/wanquota/report/daily', {}, function(data) { $('#dailyReport').html(historyTable(data)); });
    ajaxCall('/api/wanquota/report/monthly', {}, function(data) { $('#monthlyReport').html(historyTable(data)); });
    ajaxCall('/api/wanquota/report/health', {}, function(data) { $('#healthReport').html(healthTable(data)); });
}
$(document).ready(function() {
    mapDataToFormUI({'frm_wanquota_settings':'/api/wanquota/settings/get'}).done(function() { formatTokenizersUI(); $('.selectpicker').selectpicker('refresh'); });
    refreshReports();
    refreshConsumers();
    if (window.location.hash) {
        const tab = $('a[href="' + window.location.hash + '"]');
        if (tab.length) tab.tab('show');
    }
    $('#maintabs a').on('shown.bs.tab', function(event) {
        history.replaceState(null, '', event.target.hash);
    });
    $('#refreshConsumers,#consumerPeriod').on('click change', refreshConsumers);
    $('#drillDevice,#drillDomain').on('change', refreshMatrix);
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
        });
    });
});
</script>
