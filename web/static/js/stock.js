/**
 * stock.js — standalone script for /stock/<symbol> page
 * Loads quote, chart, stats, predictions, and news for one symbol.
 */

let priceChart = null;
let currentPeriod = '1d';

// ── Helpers ───────────────────────────────────────────────────────────────────

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }

function fmtNum(n, dec = 3) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toFixed(dec);
}
function fmtLarge(n) {
    if (!n) return '—';
    if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T';
    if (n >= 1e9)  return (n / 1e9).toFixed(2)  + 'B';
    if (n >= 1e6)  return (n / 1e6).toFixed(2)  + 'M';
    return n.toLocaleString();
}
function timeAgo(isoStr) {
    if (!isoStr) return '';
    const diff = Math.round((Date.now() - new Date(isoStr.replace(' ', 'T'))) / 60000);
    if (diff < 60)  return `${diff}m ago`;
    if (diff < 1440) return `${Math.floor(diff/60)}h ago`;
    return `${Math.floor(diff/1440)}d ago`;
}

// ── Quote ─────────────────────────────────────────────────────────────────────

async function loadQuote() {
    try {
        const r = await fetch(`/api/bursa/quote/${SYMBOL}`);
        const d = await r.json();
        if (d.error || !d.price) return;

        document.getElementById('company-name').textContent = d.name || SYMBOL;
        document.getElementById('nav-symbol').textContent = `${SYMBOL.replace('.KL','')} · ${d.name || ''}`;
        document.title = `${SYMBOL.replace('.KL','')} ${d.price?.toFixed(3)} — StockSight`;

        const priceEl = document.getElementById('price');
        priceEl.textContent = `MYR ${d.price.toFixed(3)}`;

        const chg = d.change_abs ?? 0;
        const pct = d.change_pct ?? 0;
        const up = chg >= 0;
        const sign = up ? '+' : '';
        const changeEl = document.getElementById('change');
        const pctEl    = document.getElementById('change-pct');
        changeEl.textContent = `${sign}${chg.toFixed(3)}`;
        pctEl.textContent    = `(${sign}${pct.toFixed(2)}%)`;
        changeEl.className = `stock-change ${up ? 'up' : 'down'}`;
        pctEl.className    = `stock-change-pct ${up ? 'up' : 'down'}`;
        priceEl.className  = `stock-price ${up ? 'up' : 'down'}`;

        if (d.day_high && d.day_low)
            setText('day-range', `Range ${d.day_low.toFixed(3)} – ${d.day_high.toFixed(3)}`);

        // Stats
        if (d.volume)      setText('s-vol',  fmtLarge(d.volume));
        if (d.day_high)    setText('s-high', fmtNum(d.day_high));
        if (d.day_low)     setText('s-low',  fmtNum(d.day_low));
        if (d.prev_close)  setText('s-prev', fmtNum(d.prev_close));
        if (d.market_cap)  setText('s-cap',  fmtLarge(d.market_cap));
        if (d.pe_ratio)    setText('s-pe',   fmtNum(d.pe_ratio, 2));
        if (d.week52_high) setText('s-52h',  fmtNum(d.week52_high));
        if (d.week52_low)  setText('s-52l',  fmtNum(d.week52_low));
        if (d.dividend_yield) setText('s-div', (d.dividend_yield * 100).toFixed(2) + '%');
        if (d.beta)        setText('s-beta', fmtNum(d.beta, 2));
    } catch (e) {
        console.error('Quote error:', e);
    }
}

// ── Chart ─────────────────────────────────────────────────────────────────────

async function loadChart(period, btn) {
    currentPeriod = period;
    if (btn) {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    const loadingEl = document.getElementById('chart-loading');
    const canvas    = document.getElementById('price-chart');
    loadingEl.textContent = 'Loading chart…';
    show('chart-loading');
    hide('price-chart');
    if (priceChart) { priceChart.destroy(); priceChart = null; }

    try {
        const r = await fetch(`/api/bursa/chart/${SYMBOL}?period=${period}`);
        const d = await r.json();

        if (d.error || !d.times?.length) {
            loadingEl.textContent = 'No chart data available';
            return;
        }

        hide('chart-loading');
        show('price-chart');

        const prices = d.close;
        const up = prices[prices.length - 1] >= prices[0];
        const color = up ? '#00c853' : '#f5365c';

        priceChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: d.times,
                datasets: [{
                    data: prices,
                    borderColor: color,
                    backgroundColor: color + '18',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    fill: true,
                    tension: 0.3,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        displayColors: false,
                        backgroundColor: '#1a1d2b',
                        borderColor: '#252836',
                        borderWidth: 1,
                        titleColor: '#8b91a8',
                        bodyColor: '#e4e6ef',
                        padding: 10,
                        callbacks: {
                            title: ctx => ctx[0]?.label || '',
                            label: ctx => `MYR ${ctx.parsed.y.toFixed(3)}`,
                        }
                    },
                },
                scales: {
                    x: {
                        ticks: { maxTicksLimit: 8, color: '#8b91a8', font: { size: 11 } },
                        grid: { color: '#1a1d2b' }
                    },
                    y: {
                        ticks: { color: '#8b91a8', font: { size: 11 } },
                        grid: { color: '#1a1d2b' }
                    }
                }
            },
            plugins: [{
                id: 'crosshair',
                afterDraw(chart) {
                    const { ctx, chartArea, tooltip } = chart;
                    if (!tooltip._active?.length) return;
                    const x = tooltip._active[0].element.x;
                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(x, chartArea.top);
                    ctx.lineTo(x, chartArea.bottom);
                    ctx.lineWidth = 1;
                    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
                    ctx.setLineDash([4, 3]);
                    ctx.stroke();
                    ctx.restore();
                }
            }]
        });
    } catch (e) {
        loadingEl.textContent = 'Failed to load chart';
        console.error(e);
    }
}

// ── Predictions ───────────────────────────────────────────────────────────────

async function loadPredictions() {
    try {
        const r = await fetch(`/api/predict/history?symbol=${SYMBOL}&limit=8`);
        const d = await r.json();
        hide('pred-loading');

        const preds = d.history || d.predictions || d || [];
        if (!preds.length) { show('pred-empty'); return; }

        const actionColor = {
            'STRONG BUY': '#00e676', 'BUY': '#69f0ae',
            'HOLD': '#ffc107', 'SELL': '#ff6e40', 'STRONG SELL': '#f5365c',
        };

        const list = document.getElementById('pred-list');
        list.innerHTML = preds.map(p => {
            const action = (p.action || 'HOLD').toUpperCase();
            const color  = actionColor[action] || '#8b91a8';
            const conf   = p.confidence ? (p.confidence * 100).toFixed(0) + '%' : '—';
            const date   = (p.created_at || '').slice(0, 16).replace('T', ' ');
            return `
                <div class="pred-row">
                    <span class="pred-action" style="color:${color}">${action}</span>
                    <span class="pred-conf">${conf} confidence</span>
                    <span class="pred-price">@ MYR ${fmtNum(p.price)}</span>
                    <span class="pred-date">${date}</span>
                </div>`;
        }).join('');
        show('pred-list');
    } catch {
        setText('pred-loading', 'Failed to load predictions');
    }
}

// ── News ──────────────────────────────────────────────────────────────────────

async function loadNews() {
    try {
        // Get all stored news, filter client-side by symbol name keywords
        const r = await fetch('/api/news/all?limit=300');
        const d = await r.json();
        hide('news-loading');

        const name = (document.getElementById('company-name').textContent || SYMBOL).toLowerCase();
        const ticker = SYMBOL.replace('.KL', '').toLowerCase();

        const keywords = [ticker, name.split(' ')[0]].filter(Boolean);
        const articles = (d.news || []).filter(a => {
            const text = ((a.headline || '') + ' ' + (a.summary || '')).toLowerCase();
            return keywords.some(kw => kw.length > 2 && text.includes(kw));
        }).slice(0, 15);

        if (!articles.length) { show('news-empty'); return; }

        const list = document.getElementById('news-list');
        list.innerHTML = articles.map(a => {
            const sentClass = a.sentiment_label || 'neutral';
            const score = a.sentiment_score != null
                ? (a.sentiment_score >= 0 ? '+' : '') + Number(a.sentiment_score).toFixed(3)
                : '';
            const url = a.url ? `href="${a.url}" target="_blank" rel="noopener"` : '';
            const ago = timeAgo(a.fetched_at);
            return `
                <div class="stock-news-item">
                    <a class="stock-news-headline" ${url}>${a.headline || '—'}</a>
                    <div class="stock-news-meta">
                        <span class="sentiment-badge ${sentClass}">${sentClass} ${score}</span>
                        <span>${a.source_name || ''}</span>
                        <span>${ago}</span>
                    </div>
                </div>`;
        }).join('');
        show('news-list');
    } catch {
        setText('news-loading', 'Failed to load news');
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

(async function init() {
    await loadQuote();
    loadChart('1d', document.querySelector('.period-btn.active'));
    loadPredictions();
    loadNews();
})();
