/* ===== app.js — Core namespace, state, API wrapper, chart factory, toast, utils ===== */

const App = {
    // ── Centralised State ────────────────────────────────────────────────────
    state: {
        market: 'US',
        charts: {},          // keyed by name, e.g. App.state.charts.price
        news:   { hoursBack: 24, statusTimer: null },
        bursa:  { symbol: null, period: '1d', refreshTimer: null, klciData: null,
                  detailSymbol: null, detailPeriod: '1d', detailChart: null, autoRefresh: true },
        modal:  { chart: null, symbol: null, period: '1d' },
        cache:  { names: {}, prices: {}, _ts: {} },  // _ts tracks cache timestamps
        loading: new Set(),
        online: true,
    },

    // Cache TTL in milliseconds (5 minutes)
    CACHE_TTL: 5 * 60 * 1000,

    // ── DOM Helpers ──────────────────────────────────────────────────────────
    $(id) { return document.getElementById(id); },

    show(id) { const el = document.getElementById(id); if (el) el.classList.remove('hidden'); },
    hide(id) { const el = document.getElementById(id); if (el) el.classList.add('hidden'); },

    setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    },

    // Escape HTML to prevent XSS when inserting user/API data
    esc(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    },

    // ── Colour / Display Helpers ─────────────────────────────────────────────
    actionClass(action) {
        return (action || '').toLowerCase().replace(/\s+/g, '-');
    },

    actionColor(action) {
        const colors = {
            'STRONG BUY': '#00e676', 'BUY': '#69f0ae', 'HOLD': '#ffc107',
            'SELL': '#ff6e40', 'STRONG SELL': '#ff1744',
        };
        return colors[action] || '#ffc107';
    },

    signalColor(signal) {
        if (signal === 'bullish')  return '#00c853';
        if (signal === 'bearish') return '#ff1744';
        return '#ffc107';
    },

    timeAgo(isoStr) {
        if (!isoStr) return 'never';
        const then = new Date(isoStr.replace(' ', 'T') + 'Z');
        const diffMin = Math.round((Date.now() - then) / 60000);
        if (diffMin < 1)  return 'just now';
        if (diffMin < 60) return `${diffMin}m ago`;
        const hrs  = Math.floor(diffMin / 60);
        const mins = diffMin % 60;
        return mins > 0 ? `${hrs}h ${mins}m ago` : `${hrs}h ago`;
    },

    // ── Toast Notifications ──────────────────────────────────────────────────
    toast(msg, type = 'info', title = '') {
        const icons = { error: '\u2715', success: '\u2713', info: '\u2139', warn: '\u26A0' };
        const defaultTitles = { error: 'Error', success: 'Success', info: 'Info', warn: 'Warning' };
        const container = App.$('toast-container');
        if (!container) return;

        const t = document.createElement('div');
        t.className = `toast toast-${type}`;

        const icon = document.createElement('span');
        icon.className = 'toast-icon';
        icon.textContent = icons[type] || '\u2139';

        const body = document.createElement('div');
        body.className = 'toast-body';
        const titleEl = document.createElement('div');
        titleEl.className = 'toast-title';
        titleEl.textContent = title || defaultTitles[type] || '';
        const msgEl = document.createElement('div');
        msgEl.className = 'toast-msg';
        msgEl.textContent = msg;
        body.appendChild(titleEl);
        body.appendChild(msgEl);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'toast-close';
        closeBtn.textContent = '\u2715';
        closeBtn.addEventListener('click', () => t.remove());

        t.appendChild(icon);
        t.appendChild(body);
        t.appendChild(closeBtn);
        container.appendChild(t);

        const duration = type === 'error' ? 6000 : 3500;
        setTimeout(() => {
            t.classList.add('toast-out');
            setTimeout(() => t.remove(), 220);
        }, duration);
    },

    // ── Network Error Banner ─────────────────────────────────────────────────
    _networkBanner: null,
    _networkRetries: 0,

    showNetworkError(msg) {
        if (!App._networkBanner) {
            const banner = document.createElement('div');
            banner.className = 'network-banner';
            banner.id = 'network-banner';
            const text = document.createElement('span');
            text.className = 'network-banner-text';
            const retryBtn = document.createElement('button');
            retryBtn.className = 'retry-btn';
            retryBtn.textContent = 'Retry';
            retryBtn.addEventListener('click', () => {
                App.hideNetworkError();
                window.location.reload();
            });
            banner.appendChild(text);
            banner.appendChild(retryBtn);
            document.body.prepend(banner);
            App._networkBanner = banner;
        }
        App._networkBanner.querySelector('.network-banner-text').textContent = msg || 'Connection lost — server may be down';
        App._networkBanner.classList.add('visible');
        App.state.online = false;
    },

    hideNetworkError() {
        if (App._networkBanner) App._networkBanner.classList.remove('visible');
        App.state.online = true;
        App._networkRetries = 0;
    },

    // ── API Wrapper — standardised fetch + error handling ────────────────────
    async api(url, opts = {}) {
        try {
            const res = await fetch(url, opts);
            if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            // Connection recovered
            if (!App.state.online) App.hideNetworkError();
            return data;
        } catch (err) {
            if (err instanceof TypeError && err.message.includes('fetch')) {
                // Network error (server down, offline, etc.)
                App._networkRetries++;
                App.showNetworkError(`Connection lost \u2014 retry ${App._networkRetries}`);
            }
            throw err;
        }
    },

    // Fire-and-forget fetch that swallows errors (for non-critical calls)
    async apiSilent(url, opts = {}) {
        try { return await App.api(url, opts); }
        catch { return null; }
    },

    // ── Data Cache with TTL ──────────────────────────────────────────────────
    cacheSet(key, data) {
        App.state.cache[key] = data;
        App.state.cache._ts[key] = Date.now();
    },

    cacheGet(key) {
        const ts = App.state.cache._ts[key];
        if (!ts || Date.now() - ts > App.CACHE_TTL) return null;
        return App.state.cache[key];
    },

    // Fetch with cache — returns cached data if fresh, else fetches
    async cachedApi(cacheKey, url, opts = {}) {
        const cached = App.cacheGet(cacheKey);
        if (cached) return cached;
        const data = await App.api(url, opts);
        App.cacheSet(cacheKey, data);
        return data;
    },

    // ── Skeleton Helpers ─────────────────────────────────────────────────────
    showSkeleton(containerId, count = 3, type = 'card') {
        const el = App.$(containerId);
        if (!el) return;
        const frag = document.createDocumentFragment();
        for (let i = 0; i < count; i++) {
            const s = document.createElement('div');
            s.className = `skeleton skeleton-${type}`;
            frag.appendChild(s);
        }
        el.innerHTML = '';
        el.appendChild(frag);
    },

    hideSkeleton(containerId) {
        const el = App.$(containerId);
        if (el) el.querySelectorAll('.skeleton').forEach(s => s.remove());
    },

    // ── Chart Factory — DRY chart creation ───────────────────────────────────
    //
    //   App.chart.create('price', 'price-chart', { type:'line', data:{...}, options:{...} })
    //   App.chart.destroy('price')
    //
    chart: {
        // Common dark-theme defaults shared by all charts
        GRID: { color: '#1e2235' },
        GRID_HIDDEN: { display: false },
        TICK_COMPACT: { color: '#8b91a8', font: { size: 10 }, maxTicksLimit: 6 },

        // Standardized dark tooltip used by ALL charts
        TOOLTIP: {
            backgroundColor: '#1a1d2b',
            borderColor: '#252836',
            borderWidth: 1,
            titleColor: '#8b91a8',
            bodyColor: '#e4e6ef',
            padding: 8,
            cornerRadius: 6,
            displayColors: true,
        },

        destroy(key) {
            const c = App.state.charts[key];
            if (c) { c.destroy(); App.state.charts[key] = null; }
        },

        create(key, canvasId, config) {
            App.chart.destroy(key);
            const canvas = App.$(canvasId);
            if (!canvas) return null;
            // Inject standardized dark tooltip into every chart
            if (config.options) {
                config.options.plugins = config.options.plugins || {};
                config.options.plugins.tooltip = {
                    ...App.chart.TOOLTIP,
                    ...(config.options.plugins.tooltip || {}),
                };
            }
            const inst = new Chart(canvas, config);
            App.state.charts[key] = inst;
            return inst;
        },

        // Shorthand: simple line chart with sensible dark-theme defaults
        line(key, canvasId, labels, datasets, extraOpts = {}) {
            return App.chart.create(key, canvasId, {
                type: 'line',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { intersect: false, mode: 'index' },
                    scales: {
                        x: { grid: App.chart.GRID_HIDDEN, ticks: { maxTicksLimit: 12 } },
                        y: { grid: App.chart.GRID },
                    },
                    plugins: { legend: { labels: { padding: 16 } } },
                    ...extraOpts,
                },
            });
        },

        // Shorthand: bar chart
        bar(key, canvasId, labels, datasets, extraOpts = {}) {
            return App.chart.create(key, canvasId, {
                type: 'bar',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: App.chart.GRID_HIDDEN, ticks: { maxTicksLimit: 12 } },
                        y: { grid: App.chart.GRID },
                    },
                    plugins: { legend: { display: false } },
                    ...extraOpts,
                },
            });
        },

        // Shorthand: doughnut chart
        doughnut(key, canvasId, labels, data, colors, extraOpts = {}) {
            return App.chart.create(key, canvasId, {
                type: 'doughnut',
                data: {
                    labels,
                    datasets: [{ data, backgroundColor: colors, borderWidth: 0 }],
                },
                options: {
                    cutout: '60%',
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } },
                    },
                    ...extraOpts,
                },
            });
        },

        // Shorthand: simple price line (Bursa detail / modal style)
        priceLine(key, canvasId, labels, prices, extraOpts = {}, plugins = []) {
            const up = prices.length > 1 ? prices[prices.length - 1] >= prices[0] : true;
            const color = up ? '#00c853' : '#f5365c';
            return App.chart.create(key, canvasId, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        data: prices,
                        borderColor: color,
                        backgroundColor: color + '18',
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: true,
                        tension: 0.3,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            displayColors: false,
                            callbacks: { label: ctx => `MYR ${ctx.parsed.y.toFixed(3)}` },
                        },
                    },
                    scales: {
                        x: { ticks: { maxTicksLimit: 6, color: '#8b91a8', font: { size: 10 } }, grid: { color: '#1a1d2b' } },
                        y: { ticks: { color: '#8b91a8', font: { size: 10 } }, grid: { color: '#1a1d2b' } },
                    },
                    ...extraOpts,
                },
                plugins,
            });
        },
    },

    // ── Name / Price Resolution Caches ───────────────────────────────────────
    async resolveNames(symbols) {
        const missing = symbols.filter(s => !App.state.cache.names[s]);
        if (!missing.length) return;
        const map = await App.apiSilent(`/api/names?symbols=${missing.join(',')}`);
        if (map) Object.assign(App.state.cache.names, map);
    },

    async resolvePrices(symbols) {
        const missing = symbols.filter(s => !App.state.cache.prices[s]);
        if (!missing.length) return;
        const map = await App.apiSilent(`/api/prices?symbols=${missing.join(',')}`);
        if (map) Object.assign(App.state.cache.prices, map);
    },

    // ── Tab API (populated by main.js) ───────────────────────────────────────
    tabs: {},
};

// Chart.js global dark theme defaults
Chart.defaults.color = '#9aa0b0';
Chart.defaults.borderColor = '#2a2e3f';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

window.App = App;
