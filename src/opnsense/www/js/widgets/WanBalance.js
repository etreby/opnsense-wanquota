/*
 * Which WAN is carrying the household's traffic, and why.
 *
 * The share is the figure that matters and the weight is not it: a gateway in a
 * lower tier receives nothing whatever its weight, so this widget leads with the
 * percentage the plugin computed from the tier layout and the weights together.
 * Reads the stored plan through the read-only report endpoint, so a dashboard can
 * show this without being handed the endpoint that can change routing.
 */
export default class WanBalance extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 300;
    }

    getGridOptions() { return { sizeToContent: 460 }; }
    getMarkup() {
        const container = $('<div class="wanbalance-widget"></div>');
        container.append($('<div id="wanbalance-verdict" style="margin-bottom:8px"></div>'));
        container.append(this.createTable('wanbalance-table', { headerPosition: 'none' }));
        return container;
    }
    _gb(value) { return `${(Number(value || 0) / 1000000000).toFixed(1)} GB`; }
    _escape(value) {
        const element = document.createElement('div');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    }
    _bar(percent) {
        const width = Math.max(0, Math.min(100, Number(percent || 0)));
        return `<div style="height:6px;background:#e8edf0;border-radius:4px;margin-top:4px;overflow:hidden">`
             + `<div style="height:100%;width:${width}%;background:${width > 0 ? '#1677a8' : 'transparent'}"></div></div>`;
    }

    async onWidgetTick() {
        const data = await this.ajaxCall('/api/wanquota/report/balance');
        if (!data?.providers?.length) {
            this.displayError(this.translations.unavailable);
            return;
        }
        const drain = data.drain || {};
        const state = data.state === 'live' ? this.translations.live
            : data.state === 'dry_run' ? this.translations.dryrun : this.translations.off;
        $('#wanbalance-verdict').html(
            `<small><b>${this._escape(state)}</b>`
            + (drain.engaged
                ? ` &middot; ${this.translations.carrying}: <b>${this._escape(drain.target)}</b>`
                : ` &middot; ${this.translations.sharing}`)
            + `</small>`);

        const rows = [[
            `<b>${this.translations.provider}</b>`,
            `<b>${this.translations.share}</b>`,
            `<b>${this.translations.headroom}</b>`,
            `<b>${this.translations.renews}</b>`
        ]];
        for (const item of data.providers) {
            const share = Number(item.share_percent || 0);
            rows.push([
                `<a href="/ui/wanquota/general/index"><b>${this._escape(item.name)}</b></a>`
                + `<br><small>${this._escape(item.gateway || item.logical_interface)}</small>`,
                `<b>${share.toFixed(share < 10 ? 1 : 0)}%</b>${this._bar(share)}`
                + (share === 0 ? `<small>${this.translations.standby}</small>` : ''),
                `${this._gb(item.urgency)}/${this.translations.day}`
                + `<br><small>${this._gb(item.remaining)} ${this.translations.left}</small>`,
                `${item.days_left} ${this.translations.days}`
            ]);
        }
        super.updateTable('wanbalance-table', rows);
    }
}
