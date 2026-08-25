/*
 * Devices the firewall is currently keeping off the internet.
 *
 * Two causes, kept apart because they mean different things: a block is something
 * somebody decided, an over-budget entry is something a measurement decided. An
 * empty widget says so plainly rather than looking broken — "nothing is blocked" is
 * the answer most of the time and is worth stating.
 */
export default class WanAccess extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 400 }; }
    getMarkup() {
        const container = $('<div class="wanaccess-widget"></div>');
        container.append(this.createTable('wanaccess-table', { headerPosition: 'none' }));
        return container;
    }
    _gb(value) { return `${(Number(value || 0) / 1000000000).toFixed(2)} GB`; }
    _escape(value) {
        const element = document.createElement('div');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    }
    _until(stamp) {
        if (!stamp) return this.translations.indefinite;
        return new Date(Number(stamp) * 1000).toLocaleString();
    }

    async onWidgetTick() {
        const data = await this.ajaxCall('/api/wanquota/report/access');
        if (!data || data.status !== 'ok') {
            this.displayError(this.translations.unavailable);
            return;
        }
        const blocked = data.blocked || [];
        const over = data.over_budget || [];
        if (!blocked.length && !over.length) {
            /* Say the quiet answer rather than showing an empty frame. */
            super.updateTable('wanaccess-table', [[
                `<small>${this.translations.nothing}</small>`
            ]]);
            return;
        }
        const rows = [[
            `<b>${this.translations.device}</b>`,
            `<b>${this.translations.why}</b>`,
            `<b>${this.translations.until}</b>`
        ]];
        for (const item of blocked) {
            rows.push([
                `<a href="/ui/wanquota/general/index#limits"><b>${this._escape(item.name)}</b></a>`
                + `<br><small>${this._escape(item.device)}</small>`,
                `<span class="label label-danger">${this.translations.blocked}</span>`
                + (item.reason ? `<br><small>${this._escape(item.reason)}</small>` : ''),
                `<small>${this._escape(this._until(item.until))}</small>`
            ]);
        }
        for (const item of over) {
            rows.push([
                `<a href="/ui/wanquota/general/index#limits"><b>${this._escape(item.name)}</b></a>`
                + `<br><small>${this._escape(item.device)}</small>`,
                `<span class="label label-warning">${this.translations.overbudget}</span>`
                + `<br><small>${this._gb(item.total)} / ${this._gb(item.budget)}</small>`,
                /* An over-budget device is released by the month turning, not a deadline. */
                `<small>${this.translations.monthend}</small>`
            ]);
        }
        if (data.budget_state === 'disabled' && over.length) {
            rows.push([`<small>${this.translations.enforcementoff}</small>`, '', '']);
        }
        super.updateTable('wanaccess-table', rows);
    }
}
