export default class WanConsumers extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 500 }; }
    getMarkup() {
        const container = $('<div class="wan-consumers-widget"></div>');
        container.append(this.createTable('wan-consumers-table', { headerPosition: 'none' }));
        container.append('<a class="btn btn-default btn-xs pull-right" style="margin-top:10px" href="/ui/wanquota/general/index#consumers"><i class="fa fa-users"></i>&nbsp; Devices &amp; domains</a><div class="clearfix"></div>');
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
        if (!data?.hosts?.length) {
            this.displayError(this.translations.unavailable);
            return;
        }
        const rows = [[
            `<b>${this.translations.device}</b>`,
            `<b>${this.translations.download}</b>`,
            `<b>${this.translations.upload}</b>`,
            `<b>${this.translations.total}</b>`
        ]];
        for (const item of data.hosts.slice(0, 10)) {
            rows.push([
                `<a href="/ui/wanquota/general/index#consumers"><b>${this._escape(item.name)}</b></a><br><small><i class="fa fa-desktop"></i> ${this._escape(item.ip)}</small>`,
                this._gb(item.download),
                this._gb(item.upload),
                `<b>${this._gb(item.total)}</b>`
            ]);
        }
        super.updateTable('wan-consumers-table', rows);
    }
}
