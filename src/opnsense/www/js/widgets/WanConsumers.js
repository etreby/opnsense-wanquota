export default class WanConsumers extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 500 }; }
    getMarkup() { return this.createTable('wan-consumers-table', { headerPosition: 'none' }); }
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
                `<b>${this._escape(item.name)}</b><br><small>${this._escape(item.ip)}</small>`,
                this._gb(item.download),
                this._gb(item.upload),
                `<b>${this._gb(item.total)}</b>`
            ]);
        }
        super.updateTable('wan-consumers-table', rows);
    }
}
