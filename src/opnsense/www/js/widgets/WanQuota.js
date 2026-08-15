export default class WanQuota extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 520 }; }
    getMarkup() {
        const container = $('<div class="wanquota-widget"></div>');
        container.append(this.createTable('wanquota-table', { headerPosition: 'none' }));
        container.append('<a class="btn btn-default btn-xs pull-right" style="margin-top:10px" href="/ui/wanquota/general/index"><i class="fa fa-line-chart"></i>&nbsp; Open full report</a><div class="clearfix"></div>');
        return container;
    }
    _gb(value) { return `${(Number(value || 0) / 1000000000).toFixed(2)} GB`; }
    _meter(value, warning) {
        const width = Math.max(0, Math.min(100, Number(value || 0)));
        const color = warning ? '#d9534f' : width >= 65 ? '#f0ad4e' : '#5cb85c';
        return `<div style="height:6px;background:#e8edf0;border-radius:4px;margin-top:4px;overflow:hidden"><div style="height:100%;width:${width}%;background:${color}"></div></div>`;
    }
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
                `<a href="/ui/wanquota/general/index"><b>${this._escape(item.name)}${warning}</b></a><br><small>${this._escape(item.start)} – ${this._escape(item.end)}${note}<br><i class="fa fa-random"></i> ${this._escape(item.interface)}</small>`,
                this._gb(item.rx),
                this._gb(item.tx),
                `${this._gb(item.used)} (${pct}%)${this._meter(pct, item.warning)}`,
                `${this._gb(item.remaining)}<br><small>${item.days_left} ${this.translations.days}; ${this._gb(item.daily_budget)}/${this.translations.day}</small>`
            ]);
        }
        super.updateTable('wanquota-table', rows);
    }
}
