/* ===== tab-trends.js — Prediction Trends tab ===== */

(function () {

    async function loadTrend() {
        const symbol = App.$('trend-symbol-input').value.trim().toUpperCase();
        if (!symbol) return;

        const days = App.$('trend-days-select').value;
        App.show('trends-loading');
        App.hide('trend-chart-section');

        try {
            const data = await App.api(`/api/predictions/trend/${symbol}?days=${days}`);
            App.hide('trends-loading');

            if (!data.trend || data.trend.length === 0) {
                App.hide('trend-empty-state');
                App.setText('trend-no-data-symbol', symbol);
                App.show('trend-no-data-state');
                return;
            }

            App.hide('trend-no-data-state');
            App.hide('trend-empty-state');
            renderTrendCharts(symbol, data.trend);
            App.show('trend-chart-section');
        } catch (err) {
            App.hide('trends-loading');
            App.toast(err.message, 'error');
        }

        loadTrackedSymbols();
    }

    function renderTrendCharts(symbol, trend) {
        App.setText('trend-chart-symbol', symbol);

        const labels      = trend.map(t => t.created_at.replace('T', ' ').slice(0, 16));
        const scores      = trend.map(t => t.score);
        const confidences = trend.map(t => t.confidence);
        const prices      = trend.map(t => t.price);
        const actions     = trend.map(t => t.action);

        const compactTicks = { color: '#8b91a8', font: { size: 10 }, maxTicksLimit: 6 };
        const compactGrid  = { color: '#1e2235' };

        // Score trend
        App.chart.create('trendScore', 'trend-score-chart', {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Prediction Score', data: scores,
                    borderColor: '#2979ff', backgroundColor: 'rgba(41,121,255,0.1)',
                    fill: true, borderWidth: 2, pointRadius: 3,
                    pointBackgroundColor: scores.map(s => s > 0.15 ? '#00c853' : s < -0.15 ? '#ff1744' : '#ffc107'),
                    tension: 0.3,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { ...compactTicks, maxRotation: 0 } },
                    y: { grid: compactGrid, ticks: compactTicks, min: -1, max: 1 },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { afterLabel: ctx => `Action: ${actions[ctx.dataIndex]}` } },
                },
            },
            plugins: [{
                id: 'zeroLine',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    const yPos = y.getPixelForValue(0);
                    ctx.strokeStyle = '#444'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    ctx.beginPath(); ctx.moveTo(left, yPos); ctx.lineTo(right, yPos); ctx.stroke();
                    ctx.setLineDash([]);
                },
            }],
        });

        // Confidence trend
        App.chart.create('trendConfidence', 'trend-confidence-chart', {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Confidence', data: confidences,
                    borderColor: '#7c4dff', backgroundColor: 'rgba(124,77,255,0.1)',
                    fill: true, borderWidth: 2, pointRadius: 2, tension: 0.3,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { ...compactTicks, maxRotation: 0 } },
                    y: { grid: compactGrid, ticks: compactTicks, min: 0, max: 1 },
                },
                plugins: { legend: { display: false } },
            },
        });

        // Price vs Score (dual axis)
        const isMY = symbol.endsWith('.KL');
        App.chart.create('trendPrice', 'trend-price-chart', {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: isMY ? 'Price (MYR)' : 'Price ($)', data: prices, borderColor: '#00e5ff', borderWidth: 2, pointRadius: 2, tension: 0.3, yAxisID: 'y' },
                    { label: 'Score', data: scores, borderColor: '#ff6e40', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 2, tension: 0.3, yAxisID: 'y1' },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: { grid: { display: false }, ticks: { ...compactTicks, maxRotation: 0 } },
                    y:  { type: 'linear', position: 'left', grid: compactGrid, ticks: compactTicks },
                    y1: { type: 'linear', position: 'right', min: -1, max: 1, grid: { drawOnChartArea: false }, ticks: compactTicks },
                },
                plugins: { legend: { labels: { font: { size: 10 }, boxWidth: 10, padding: 8 } } },
            },
        });
    }

    // ── Tracked Symbols ──────────────────────────────────────────────────────

    async function loadTrackedSymbols() {
        try {
            const data = await App.api('/api/predictions/symbols');
            const list = App.$('tracked-symbols-list');
            if (!list || !data.symbols?.length) return;

            await App.resolveNames(data.symbols.map(s => s.symbol));

            list.innerHTML = '';
            const label = document.createElement('span');
            label.textContent = 'Tracked:';
            list.appendChild(label);

            data.symbols.forEach(s => {
                const name = App.state.cache.names[s.symbol] || s.symbol;
                const btn = document.createElement('button');
                btn.textContent = `${name} (${s.count})`;
                btn.title = s.symbol;
                btn.addEventListener('click', () => quickTrend(s.symbol));
                list.appendChild(btn);
            });
            list.style.display = 'flex';
        } catch {}
    }

    function quickTrend(symbol) {
        App.$('trend-symbol-input').value = symbol;
        loadTrend();
    }

    function goAnalyze() {
        const symbol = App.$('trend-symbol-input').value.trim();
        // Switch to Analysis tab
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.querySelector('[data-tab="stock-tab"]').classList.add('active');
        App.$('stock-tab').classList.add('active');
        // Update aria
        document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', t.classList.contains('active')));
        // Pre-fill and analyze
        App.$('symbol-input').value = symbol;
        if (symbol.endsWith('.KL')) App.tabs.analysis.switchMarket('MY');
        else App.tabs.analysis.switchMarket('US');
        App.tabs.analysis.analyze();
    }

    // ── Prediction History ───────────────────────────────────────────────────

    async function loadHistory() {
        App.show('trends-loading');
        App.hide('history-section');
        App.hide('history-empty');

        try {
            const data = await App.api('/api/predictions/history?limit=200');
            const preds = data.predictions || [];
            if (!preds.length) {
                App.hide('trends-loading');
                App.show('history-empty');
                return;
            }

            const uniqueSymbols = [...new Set(preds.map(p => p.symbol).filter(Boolean))];
            await App.resolveNames(uniqueSymbols);

            const missingPriceSymbols = [...new Set(preds.filter(p => !p.price).map(p => p.symbol).filter(Boolean))];
            App.hide('trends-loading');

            const tbody = App.$('history-tbody');
            tbody.innerHTML = '';

            const countEl = App.$('history-count');
            if (countEl) countEl.textContent = `${preds.length} predictions`;

            const actionColors = {
                'STRONG BUY':  { bg: '#00e676', text: '#001a0a' },
                'BUY':         { bg: '#69f0ae', text: '#001a0a' },
                'HOLD':        { bg: '#ffc107', text: '#1a1200' },
                'SELL':        { bg: '#ff6e40', text: '#1a0800' },
                'STRONG SELL': { bg: '#f5365c', text: '#1a0008' },
            };

            const frag = document.createDocumentFragment();
            preds.forEach(p => {
                const action = (p.action || 'HOLD').toUpperCase();
                const col  = actionColors[action] || { bg: '#8b91a8', text: '#0d0e14' };
                const conf = p.confidence ? (p.confidence * 100).toFixed(0) + '%' : '\u2014';
                const score = p.score != null ? (p.score >= 0 ? '+' : '') + Number(p.score).toFixed(3) : '\u2014';
                const scoreColor = p.score > 0 ? '#00c853' : p.score < 0 ? '#ff1744' : '#ffc107';
                const isMY = (p.symbol || '').endsWith('.KL');
                const priceStr = p.price ? (isMY ? 'MYR ' : '$') + Number(p.price).toFixed(isMY ? 3 : 2) : '\u2014';
                const ago = App.timeAgo(p.created_at);
                const displayName = App.state.cache.names[p.symbol] || p.symbol || '\u2014';
                const pricePending = !p.price && missingPriceSymbols.includes(p.symbol);

                const row = document.createElement('div');
                row.className = 'trend-hist-row';
                row.addEventListener('click', () => quickTrend(p.symbol));

                const symSpan = document.createElement('span');
                symSpan.className = 'trend-hist-sym';
                symSpan.textContent = displayName;

                const actSpan = document.createElement('span');
                actSpan.className = 'trend-hist-action';
                actSpan.style.background = col.bg;
                actSpan.style.color = col.text;
                actSpan.textContent = action;

                const dateSpan = document.createElement('span');
                dateSpan.className = 'trend-hist-date';
                dateSpan.textContent = ago;

                const subSpan = document.createElement('span');
                subSpan.className = 'trend-hist-sub';

                const priceVal = document.createElement('span');
                priceVal.className = 'hist-price-val';
                if (pricePending) {
                    priceVal.dataset.priceSym = p.symbol;
                    priceVal.dataset.isMy = String(isMY);
                }
                priceVal.textContent = priceStr;

                const scoreSpan = document.createElement('span');
                scoreSpan.style.color = scoreColor;
                scoreSpan.textContent = score;

                subSpan.append(
                    document.createTextNode(`${p.symbol} \u00B7 `),
                    priceVal,
                    document.createTextNode(` \u00B7 ${conf} conf \u00B7 `),
                    scoreSpan,
                );

                row.append(symSpan, actSpan, dateSpan, subSpan);
                frag.appendChild(row);
            });
            tbody.appendChild(frag);

            App.show('history-section');
            loadTrackedSymbols();

            // Back-fill live prices
            if (missingPriceSymbols.length) {
                App.resolvePrices(missingPriceSymbols).then(() => {
                    tbody.querySelectorAll('[data-price-sym]').forEach(el => {
                        const sym = el.dataset.priceSym;
                        const isMY = el.dataset.isMy === 'true';
                        const price = App.state.cache.prices[sym];
                        if (price) el.textContent = (isMY ? 'MYR ' : '$') + price.toFixed(isMY ? 3 : 2);
                    });
                });
            }
        } catch (err) {
            App.hide('trends-loading');
            App.show('history-empty');
            console.error('History error:', err);
        }
    }

    // ── Sector History ───────────────────────────────────────────────────────

    async function loadSectorHistory() {
        App.show('sector-trend-loading');
        App.hide('sector-history-section');

        try {
            const data = await App.api('/api/sectors/history');
            App.hide('sector-trend-loading');

            const history = data.history || [];
            if (!history.length) {
                App.toast('No sector history yet \u2014 run sector analysis first.', 'warn', 'No Data');
                return;
            }

            const bySector = {};
            history.forEach(h => {
                if (!bySector[h.sector_name]) bySector[h.sector_name] = [];
                bySector[h.sector_name].push(h);
            });

            const sectorColors = ['#2979ff', '#00e5ff', '#7c4dff', '#ffc107', '#ff6e40', '#00c853', '#ff1744', '#e040fb', '#18ffff', '#ffab40', '#69f0ae'];

            App.chart.create('sectorTrend', 'sector-trend-chart', {
                type: 'line',
                data: {
                    datasets: Object.entries(bySector).map(([name, entries], i) => ({
                        label: name,
                        data: entries.map(e => ({ x: e.created_at, y: e.score })),
                        borderColor: sectorColors[i % sectorColors.length],
                        borderWidth: 2, pointRadius: 3, tension: 0.3, fill: false,
                    })),
                },
                options: {
                    responsive: true,
                    scales: {
                        x: { type: 'category', grid: { display: false } },
                        y: { grid: { color: '#1e2235' }, min: -1, max: 1 },
                    },
                    plugins: { legend: { position: 'bottom', labels: { padding: 12 } } },
                },
            });

            App.show('sector-history-section');
        } catch (err) {
            App.hide('sector-trend-loading');
            App.toast(err.message, 'error');
        }
    }

    App.tabs.trends = { loadTrend, loadHistory, loadSectorHistory, goAnalyze, quickTrend };
})();
