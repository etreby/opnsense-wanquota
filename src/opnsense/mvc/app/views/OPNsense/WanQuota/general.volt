<script src="{{ cache_safe('/ui/js/chart.umd.min.js') }}"></script>
<style>
.wq-shell{--wq-blue:#3b82f6;--wq-cyan:#06b6d4;--wq-green:#10b981;--wq-amber:#f59e0b;--wq-red:#ef4444;--wq-ink:#172033}.wq-hero{padding:24px;border-radius:14px;background:linear-gradient(135deg,#172033,#253656 60%,#1677a8);color:#fff;margin-bottom:18px;box-shadow:0 12px 30px rgba(23,32,51,.18)}.wq-hero h2{margin:0 0 5px;font-weight:700}.wq-hero p{margin:0;opacity:.8}.wq-hero-tools{float:right;display:flex;gap:6px}.wq-hero-tools .btn{background:#ffffff18;color:#fff;border-color:#ffffff4d}.wq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin:16px 0}.wq-card{background:var(--background-color,#fff);border:1px solid rgba(128,128,128,.2);border-radius:12px;padding:16px;box-shadow:0 4px 16px rgba(23,32,51,.07)}.wq-card h3{font-size:15px;margin:0 0 12px;color:inherit}.wq-metric{font-size:26px;font-weight:700;line-height:1.1}.wq-muted{opacity:.68;font-size:12px}.wq-progress{height:8px;background:rgba(128,128,128,.18);border-radius:8px;overflow:hidden;margin:12px 0}.wq-progress span{display:block;height:100%;border-radius:8px;background:linear-gradient(90deg,var(--wq-blue),var(--wq-cyan))}.wq-chart{position:relative;height:290px}.wq-chart-sm{position:relative;height:180px}.wq-section{margin-top:22px}.wq-section-title{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.wq-section-title h3{margin:0}.wq-health-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}.wq-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.wq-table-wrap{overflow-x:auto}.wq-card .table{margin-bottom:0}.wq-risk-on_track{color:var(--wq-green)}.wq-risk-watch{color:var(--wq-amber)}.wq-risk-high,.wq-risk-exceeded{color:var(--wq-red)}.wq-action-box{padding:10px 12px;border-left:4px solid var(--wq-blue);background:rgba(59,130,246,.08);border-radius:6px}.wq-wallboard .navbar,.wq-wallboard #maintabs,.wq-wallboard .wq-exact{display:none!important}.wq-wallboard .wq-chart{height:38vh}.wq-contrast .wq-card{border:2px solid currentColor;box-shadow:none}.wq-drill{cursor:pointer;border-bottom:1px dotted currentColor;text-decoration:none}.wq-drill:hover,.wq-drill:focus{text-decoration:none;border-bottom-style:solid}.wq-drill-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:12px 14px;margin-bottom:12px;border-left:4px solid var(--wq-blue);background:rgba(59,130,246,.08);border-radius:6px}.wq-drill-metric{text-align:right}.wq-share{height:8px;background:rgba(128,128,128,.18);border-radius:8px;overflow:hidden;min-width:60px}.wq-share span{display:block;height:100%;border-radius:8px}.wq-unattributed td{opacity:.7}.wq-shares{margin-top:10px;font-size:12px}.wq-share-row{display:flex;align-items:center;gap:8px;padding:2px 0}.wq-share-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}.wq-share-name{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wq-share-pct{font-weight:700;flex:0 0 auto}.wq-share-others .wq-share-name{opacity:.7;font-style:italic}
@media(max-width:767px){.wq-hero{padding:18px}.wq-chart{height:240px}.wq-metric{font-size:22px}.wq-hero-tools{float:none;margin-bottom:12px}.wq-drill-metric{text-align:left}}
</style>
<div class="wq-shell">
<div class="wq-hero"><div class="wq-hero-tools"><button id="unitToggle" class="btn btn-sm" type="button">GB</button><button id="contrastToggle" class="btn btn-sm" type="button"><i class="fa fa-adjust"></i></button><button id="wallboardToggle" class="btn btn-sm" type="button"><i class="fa fa-television"></i></button></div><h2><i class="fa fa-tachometer"></i> {{ lang._('WAN Intelligence') }}</h2><p>{{ lang._('Quota health, traffic trends, consumers and domain attribution in one place.') }}</p></div>
<ul class="nav nav-tabs" data-tabs="tabs" id="maintabs">
    <li class="active"><a data-toggle="tab" href="#summary">{{ lang._('Summary') }}</a></li>
    <li><a data-toggle="tab" href="#consumers">{{ lang._('Consumers') }}</a></li>
    <li><a data-toggle="tab" href="#daily">{{ lang._('Daily history') }}</a></li>
    <li><a data-toggle="tab" href="#monthly">{{ lang._('Monthly history') }}</a></li>
    <li><a data-toggle="tab" href="#intelligence">{{ lang._('Intelligence') }}</a></li>
    <li><a data-toggle="tab" href="#health">{{ lang._('Data health') }}</a></li>
    <li><a data-toggle="tab" href="#settings">{{ lang._('Settings') }}</a></li>
</ul>

<div class="tab-content content-box tab-content">
    <div id="summary" class="tab-pane fade in active"><div style="padding:16px"><div class="btn-group pull-right"><button id="exportSummaryCsv" class="btn btn-default" type="button"><i class="fa fa-download"></i> CSV</button><button id="exportSummaryJson" class="btn btn-default" type="button"><i class="fa fa-download"></i> JSON</button></div><div class="wq-grid" id="quotaCards"></div><div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Provider quota comparison') }}</h3><div class="wq-chart"><canvas id="quotaChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('Download and upload mix') }}</h3><div class="wq-chart"><canvas id="trafficMixChart"></canvas></div></div></div><div id="summaryReport" class="wq-section wq-table-wrap"></div></div></div>
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
    <div id="intelligence" class="tab-pane fade"><div style="padding:16px"><div class="wq-toolbar"><label>Period</label><select id="intelligencePeriod" class="form-control"><option value="today">Today</option><option value="week">7 days</option><option value="thirty" selected>30 days</option><option value="month">Current month</option></select><input id="intelligenceSearch" class="form-control" placeholder="Filter groups, categories or anomalies"><button id="refreshIntelligence" class="btn btn-primary" type="button">Refresh</button></div><div id="intelligenceCards" class="wq-grid"></div><div class="wq-action-box wq-toolbar"><b>Temporary guardrail override</b><select id="overrideProvider" class="form-control"></select><select id="overrideMode" class="form-control"><option value="observe">Observe</option><option value="deprioritize">Deprioritize</option><option value="failover">Fail over</option><option value="cutoff">Cut off</option></select><select id="overrideHours" class="form-control"><option value="1">1 hour</option><option value="6">6 hours</option><option value="24" selected>24 hours</option><option value="168">7 days</option></select><button id="applyOverride" class="btn btn-warning" type="button">Apply override</button><span id="overrideStatus" class="wq-muted">Overrides remain advisory while enforcement is disabled or dry-run.</span></div><div class="wq-grid"><div class="wq-card"><h3>{{ lang._('Device-group usage and budgets') }}</h3><div class="wq-chart"><canvas id="groupChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('App categories breakdown') }}</h3><div class="wq-chart"><canvas id="categoryChart"></canvas></div><div id="categoryShares" class="wq-shares"></div></div><div class="wq-card"><h3>{{ lang._('Traffic versus provider quality') }}</h3><div class="wq-chart"><canvas id="qualityChart"></canvas></div></div><div class="wq-card"><h3>{{ lang._('Cycle history') }}</h3><div class="wq-chart"><canvas id="cycleChart"></canvas></div></div></div><div id="categoryDrill" class="wq-section wq-table-wrap"></div><div id="intelligenceDetails" class="wq-section wq-table-wrap"></div></div></div>
    <div id="health" class="tab-pane fade"><div id="healthReport" style="padding:16px"></div></div>
    <div id="settings" class="tab-pane fade">
        <div class="content-box" style="padding-bottom:1.5em">
            {{ partial("layout_partials/base_form", ['fields':generalForm,'id':'frm_wanquota_settings']) }}
            <div class="col-md-12"><hr><button class="btn btn-primary" id="saveAct" type="button"><b>{{ lang._('Save') }}</b> <i id="saveAct_progress"></i></button></div>
        </div>
    </div>
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
function quotaCards(data) { return (data.providers||[]).map((p,i)=>{const pct=Math.min(100,Number(p.percent||0)), color=pct>=90?'#ef4444':pct>=75?'#f59e0b':wqColors[i%wqColors.length];return `<div class="wq-card"><div class="wq-muted">${esc(p.logical_interface)} → ${esc(p.interface)}</div><h3>${esc(p.name)}</h3><div class="wq-metric">${pct.toFixed(1)}%</div><div class="wq-progress"><span style="width:${pct}%;background:${color}"></span></div><div><b>${gb(p.remaining)}</b> remaining</div><div class="wq-muted">${esc(p.days_left)} days left · ${gb(p.daily_budget)}/day budget</div></div>`}).join(''); }
function renderSummaryCharts(data){const p=data.providers||[];$('#quotaCards').html(quotaCards(data));makeChart('quotaChart',{type:'bar',data:{labels:p.map(x=>x.name),datasets:[{label:'Used GB',data:p.map(x=>x.used/1e9),backgroundColor:wqColors},{label:'Remaining GB',data:p.map(x=>x.remaining/1e9),backgroundColor:'rgba(128,128,128,.25)'}]},options:chartOptions(false)});makeChart('trafficMixChart',{type:'doughnut',data:{labels:p.flatMap(x=>[x.name+' download',x.name+' upload']),datasets:[{data:p.flatMap(x=>[x.rx/1e9,x.tx/1e9]),backgroundColor:p.flatMap((x,i)=>[wqColors[i%wqColors.length],wqColors[(i+3)%wqColors.length]])}]},options:{responsive:true,maintainAspectRatio:false,cutout:'62%',plugins:{legend:{position:'bottom'}}}});}
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
            html += `<tr><td><a href="#" class="wq-drill" data-drill="domain" data-value='${esc(row.domain)}' title="Show the devices that used this site"><b>${esc(row.domain)}</b></a></td><td>${row.ip_count}</td><td><b>${gb(row.total)}</b></td></tr>`;
        }
    }
    return html + '</tbody></table>';
}
let currentSummaryData = null, currentConsumerData = null;
let currentIntelligenceData = null;
function intelligenceCards(data){const providers=data?.summary?.providers||[];return providers.map(p=>{const f=p.forecast||{},q=p.quality||{},policy=p.policy||{},movement=p.movement;const trend=movement?(movement.used_delta>=0?'▲ ':'▼ ')+gb(Math.abs(movement.used_delta))+' in 24h':'Collecting 24h comparison';return `<div class="wq-card" data-filter="${esc((p.name+' '+f.risk+' '+policy.recommended).toLowerCase())}"><div class="wq-muted">${esc(p.logical_interface)} · ${esc(q.status||'unknown')}</div><h3>${esc(p.name)}</h3><div class="wq-metric wq-risk-${esc(f.risk||'on_track')}">${esc((f.risk||'unknown').replace('_',' ').toUpperCase())}</div><div>${f.exhaustion_date?'Exhaustion '+esc(f.exhaustion_date):'Projected within allowance'}</div><div><b>${esc(trend)}</b></div><div class="wq-muted">Latency ${Number(q.latency||0).toFixed(1)} ms · Loss ${Number(q.loss||0).toFixed(1)}% · Guardrail ${esc(policy.recommended||'observe')} ${policy.dry_run?'(dry-run)':''}</div></div>`}).join('');}
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

function renderIntelligence(data){currentIntelligenceData=data;if(/^#[0-9a-f]{6}$/i.test(data?.settings?.accent||''))document.querySelector('.wq-shell').style.setProperty('--wq-blue',data.settings.accent);$('#intelligenceCards').html(intelligenceCards(data));$('#intelligenceDetails').html(intelligenceDetails(data));const groups=data.groups||[],categories=data.categories||[],providers=data?.summary?.providers||[],archives=data.archives||[];$('#overrideProvider').html(providers.map(x=>`<option value="${esc(x.name)}">${esc(x.name)}</option>`).join(''));makeChart('groupChart',{type:'bar',data:{labels:groups.map(x=>x.name),datasets:[{label:'Usage GB',data:groups.map(x=>x.total/1e9),backgroundColor:data?.settings?.accent||'#3b82f6'},{label:'Budget GB',data:groups.map(x=>x.budget?x.budget/1e9:null),backgroundColor:'rgba(128,128,128,.28)'}]},options:chartOptions(true)});renderCategoryBreakdown(data);const qualityOptions=chartOptions(false);qualityOptions.scales.y1={beginAtZero:true,position:'right',grid:{drawOnChartArea:false},title:{display:true,text:'Cycle usage GB'}};makeChart('qualityChart',{type:'bar',data:{labels:providers.map(x=>x.name),datasets:[{label:'Latency ms',data:providers.map(x=>x.quality?.latency||0),backgroundColor:'#06b6d4'},{label:'Loss %',data:providers.map(x=>x.quality?.loss||0),backgroundColor:'#ef4444'},{type:'line',label:'Cycle usage GB',data:providers.map(x=>x.used/1e9),borderColor:'#8b5cf6',backgroundColor:'#8b5cf6',yAxisID:'y1',tension:.25}]},options:qualityOptions});makeChart('cycleChart',{type:'bar',data:{labels:archives.map(x=>x.provider+' '+x.start).slice(0,12),datasets:[{label:'Used GB',data:archives.map(x=>x.used/1e9).slice(0,12),backgroundColor:'#8b5cf6'},{label:'Unused GB',data:archives.map(x=>Math.max(0,x.quota-x.used)/1e9).slice(0,12),backgroundColor:'rgba(128,128,128,.25)'}]},options:chartOptions(false)});filterIntelligence();}
function refreshIntelligence(){const period=$('#intelligencePeriod').val();ajaxCall('/api/wanquota/report/intelligence_'+period,{},renderIntelligence);}
function filterIntelligence(){const query=String($('#intelligenceSearch').val()||'').toLowerCase();$('#intelligence [data-filter]').each(function(){$(this).toggle(!query||String($(this).data('filter')).includes(query));});}
function wanTable(providers) {
    if (!providers || !providers.length) return '<div class="alert alert-info">No per-WAN download data is available.</div>';
    let html = '<table class="table table-striped"><thead><tr><th>{{ lang._('Provider') }}</th><th>{{ lang._('Attributed flow total') }}</th><th>{{ lang._('Top devices') }}</th><th>{{ lang._('Top domains') }}</th><th>{{ lang._('Direction split') }}</th></tr></thead><tbody>';
    for (const provider of providers) {
        const devices = (provider.devices || []).slice(0, 5).map(item => `<a href="#" class="wq-drill" data-drill="device" data-value='${esc(item.ip)}'>${esc(item.name)}</a> (${gb(item.total)})`).join('<br>') || '—';
        const domains = (provider.domains || []).slice(0, 5).map(item => `<a href="#" class="wq-drill" data-drill="domain" data-value='${esc(item.domain)}'>${esc(item.domain)}</a> (${gb(item.total)})`).join('<br>') || '—';
        html += `<tr><td><b>${esc(provider.name)}</b><br><small>${esc(provider.logical_interface)} → ${esc(provider.interface)}</small></td><td><b>${gb(provider.total)}</b></td><td>${devices}</td><td>${domains}</td><td><span class="text-muted">Not attributable</span><br><small>${esc(provider.direction_attribution)}</small></td></tr>`;
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
function drillTo(kind, value) {
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
    const labels = {ok: 'success', stale: 'warning', failed: 'danger', disabled: 'default'};
    const color = data.status === 'ok' ? '#10b981' : data.status === 'failed' ? '#ef4444' : '#f59e0b';
    let html = `<div class="wq-hero" style="background:linear-gradient(135deg,#172033,${color})"><h2><span class="wq-health-dot" style="background:${color};box-shadow:0 0 12px ${color}"></span>Data health: ${esc(data.status).toUpperCase()}</h2><p>All reporting depends on fresh accounting sources · ${esc(data.generated_at)}</p></div><div class="wq-grid">`;
    for (const item of data.checks) { const c=item.status==='ok'?'#10b981':item.status==='failed'?'#ef4444':'#f59e0b'; html+=`<div class="wq-card"><h3><span class="wq-health-dot" style="background:${c}"></span>${esc(item.name)}</h3><div class="wq-metric" style="font-size:18px">${esc(item.status).toUpperCase()}</div><div class="wq-muted">${esc(item.detail)}</div></div>`; }
    html += '</div>';
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
    mapDataToFormUI({'frm_wanquota_settings':'/api/wanquota/settings/get'}).done(function() { formatTokenizersUI(); $('.selectpicker').selectpicker('refresh'); });
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
    $('#intelligence').on('click', 'a.wq-drill', function(event) {
        event.preventDefault();
        const kind = $(this).data('drill'), value = $(this).data('value');
        if (kind === 'category') { showCategory(value); return; }
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
        });
    });
});
</script>
