/*
 * What each WAN is moving right now.
 *
 * The quota widget answers "how much of the month is gone"; this answers "what is
 * happening this second", which is the question you ask when something feels slow.
 * Rates come from the interface counters, so they are the link's real throughput
 * rather than anything attributed or estimated.
 */
export default class WanRates extends BaseTableWidget {
    constructor() {
        super();
        this.tickTimeout = 10;
    }

    getGridOptions() { return { sizeToContent: 340 }; }
    getMarkup() {
        const container = $('<div class="wanrates-widget"></div>');
        container.append(this.createTable('wanrates-table', { headerPosition: 'none' }));
        return container;
    }
    _rate(bits) {
        const value = Number(bits || 0);
        if (value >= 1e9) return `${(value / 1e9).toFixed(2)} Gbit/s`;
        if (value >= 1e6) return `${(value / 1e6).toFixed(1)} Mbit/s`;
        if (value >= 1e3) return `${(value / 1e3).toFixed(0)} kbit/s`;
        return `${value.toFixed(0)} bit/s`;
    }
    _escape(value) {
        const element = document.createElement('div');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    }

    async onWidgetTick() {
        const data = await this.ajaxCall('/api/wanquota/report/throughput');
        const links = data?.wans || [];
        if (!links.length) {
            this.displayError(this.translations.unavailable);
            return;
        }
        const rows = [[
            `<b>${this.translations.provider}</b>`,
            `<b>${this.translations.down}</b>`,
            `<b>${this.translations.up}</b>`
        ]];
        for (const item of links) {
            if (item.available === false) {
                /* Naming the link and the reason beats dropping the row: a missing
                   line reads as a link that does not exist. */
                rows.push([
                    `<b>${this._escape(item.name)}</b><br><small>${this._escape(item.interface)}</small>`,
                    `<small>${this._escape(item.error || this.translations.noreading)}</small>`, ''
                ]);
                continue;
            }
            rows.push([
                `<b>${this._escape(item.name)}</b><br><small>${this._escape(item.interface)}</small>`,
                `<span style="color:#1677a8">&#9660; ${this._rate(item.download_bps)}</span>`,
                `<span style="color:#7c3aed">&#9650; ${this._rate(item.upload_bps)}</span>`
            ]);
        }
        super.updateTable('wanrates-table', rows);
    }
}
