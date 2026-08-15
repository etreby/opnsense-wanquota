<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#summary">{{ lang._('Summary') }}</a></li>
    <li><a data-toggle="tab" href="#consumers">{{ lang._('Consumers') }}</a></li>
    <li><a data-toggle="tab" href="#daily">{{ lang._('Daily history') }}</a></li>
    <li><a data-toggle="tab" href="#monthly">{{ lang._('Monthly history') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>

<div class="tab-content content-box tab-content">
    <div id="summary" class="tab-pane fade in active"><div id="summaryReport" style="padding:16px"></div></div>
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
            </div>
            <h3>{{ lang._('Top LAN consumers') }}</h3><div id="hostConsumers"></div>
            <h3>{{ lang._('Top attributed domains') }}</h3><div id="domainConsumers"></div>
            <div id="domainCoverage"></div>
        </div>
    </div>
    <div id="daily" class="tab-pane fade"><div id="dailyReport" style="padding:16px"></div></div>
    <div id="monthly" class="tab-pane fade"><div id="monthlyReport" style="padding:16px"></div></div>
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
function refreshConsumers() {
    const period = $('#consumerPeriod').val();
    ajaxCall('/api/wanquota/report/consumers_' + period, {}, function(data) {
        $('#hostConsumers').html(consumerTable(data.hosts, 'name'));
        $('#domainConsumers').html(consumerTable(data.domains, 'domain'));
        const coverage = Number(data?.domain_attribution?.coverage_percent || 0).toFixed(1);
        $('#domainCoverage').html(`<div class="alert alert-info"><b>Domain attribution coverage: ${coverage}%</b><br><small>${esc(data?.domain_attribution?.method || '')}. Encrypted DNS, VPNs, ECH, shared CDN IPs, and uncached answers can remain unattributed.</small></div>`);
    });
}
function refreshReports() {
    ajaxCall('/api/wanquota/report/summary', {}, function(data) { $('#summaryReport').html(summaryTable(data)); });
    ajaxCall('/api/wanquota/report/daily', {}, function(data) { $('#dailyReport').html(historyTable(data)); });
    ajaxCall('/api/wanquota/report/monthly', {}, function(data) { $('#monthlyReport').html(historyTable(data)); });
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
    $('#saveAct').click(function() {
        $('#saveAct_progress').addClass('fa fa-spinner fa-pulse');
        saveFormToEndpoint('/api/wanquota/settings/set', 'frm_wanquota_settings', function() {
            $('#saveAct_progress').removeClass('fa fa-spinner fa-pulse');
            refreshReports();
        });
    });
});
</script>
