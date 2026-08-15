export default class WanDomains extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 480 }; }
    getMarkup() {
        const container = $('<div class="wan-domains-widget"></div>');
        container.append('<div id="wan-domains-coverage" class="text-muted" style="margin-bottom:8px"></div>');
        container.append(this.createTable('wan-domains-table', { headerPosition: 'none' }));
        container.append('<a class="btn btn-default btn-xs pull-right" style="margin-top:10px" href="/ui/wanquota/general/index#consumers"><i class="fa fa-globe"></i>&nbsp; Open domain report</a><div class="clearfix"></div>');
        return container;
    }
    _gb(value) { return `${(Number(value || 0) / 1000000000).toFixed(2)} GB`; }
    _escape(value) {
        const element = document.createElement('div');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    }

    async onWidgetTick() {
        const data = await this.ajaxCall('/api/wanquota/report/consumers_thirty');
        const coverage = Number(data?.domain_attribution?.coverage_percent || 0);
        $('#wan-domains-coverage').html(`<i class="fa fa-info-circle"></i> ${this.translations.coverage}: <b>${coverage.toFixed(1)}%</b>`);
        if (!data?.domains?.length) {
            this.displayError(this.translations.unavailable);
            return;
        }
        const rows = [[`<b>${this.translations.domain}</b>`, `<b>${this.translations.total}</b>`]];
        for (const item of data.domains.slice(0, 10)) {
            rows.push([
                `<a href="/ui/wanquota/general/index#consumers"><i class="fa fa-globe"></i>&nbsp; <b>${this._escape(item.domain)}</b></a><br><small>${Number(item.ip_count || 0)} observed IPs</small>`,
                `<b>${this._gb(item.total)}</b>`,
            ]);
        }
        super.updateTable('wan-domains-table', rows);
    }
}
