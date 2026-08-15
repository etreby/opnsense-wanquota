export default class WanQuota extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 520 }; }
    getMarkup() { return this.createTable('wanquota-table', { headerPosition: 'none' }); }
    _gb(value) { return `${(Number(value || 0) / 1000000000).toFixed(2)} GB`; }
    _escape(value) {
        const element = document.createElement('div');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    }

    async onWidgetTick() {
        const data = await this.ajaxCall('/api/wanquota/report/summary');
        if (!data?.providers?.length) {
            this.displayError(this.translations.unavailable);
            return;
        }
        const rows = [[
            `<b>${this.translations.provider}</b>`,
            `<b>${this.translations.download}</b>`,
            `<b>${this.translations.upload}</b>`,
            `<b>${this.translations.used}</b>`,
            `<b>${this.translations.remaining}</b>`
        ]];
        for (const item of data.providers) {
            const pct = Math.min(999, Number(item.percent)).toFixed(1);
            const note = item.complete ? '' : ' *';
            const warning = item.warning ? ' ⚠' : '';
            rows.push([
                `<b>${this._escape(item.name)}${warning}</b><br><small>${this._escape(item.start)} – ${this._escape(item.end)}${note}<br>${this._escape(item.interface)}</small>`,
                this._gb(item.rx),
                this._gb(item.tx),
                `${this._gb(item.used)} (${pct}%)`,
                `${this._gb(item.remaining)}<br><small>${item.days_left} ${this.translations.days}; ${this._gb(item.daily_budget)}/${this.translations.day}</small>`
            ]);
        }
        super.updateTable('wanquota-table', rows);
    }
}
