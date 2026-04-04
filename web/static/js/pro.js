/* ===== Pro Dashboard - Bloomberg Terminal Style ===== */

// ===== STATE =====
let activeMarket = 'US';
let activeSymbol = 'SPY';
let activeTimeframe = '6mo';
let myStockNames = {};  // Loaded from API

const WATCHLISTS = {
    US: ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'JPM'],
    MY: ['1155.KL', '1295.KL', '1023.KL', '5347.KL', '5183.KL', '5225.KL', '6888.KL', '6947.KL', '5819.KL', '8869.KL'],
};
const MARKET_DEFAULTS = { US: 'SPY', MY: '1155.KL' };

let watchlist = [...WATCHLISTS.US];
let watchlistData = {};
let refreshInterval = null;
let refreshRate = 30;

// Charts
let mainChart, miniRsi, miniMacd, miniVol;

// ===== CHART DEFAULTS =====
Chart.defaults.color = '#6b7280';
Chart.defaults.borderColor = '#1c2030';
Chart.defaults.font.family = "'SF Mono', 'Fira Code', 'Consolas', monospace";
Chart.defaults.font.size = 10;

// ===== INIT =====
document.addEventListener('DOMContentLoaded', async () => {
    // Load market config (stock names etc.)
    try {
        const res = await fetch('/api/markets');
        const data = await res.json();
        myStockNames = data.my_stock_names || {};
    } catch (e) { /* ignore */ }

    updateClock();
    setInterval(updateClock, 1000);
    refreshWatchlist();
    setRefreshRate();
    selectStock(MARKET_DEFAULTS[activeMarket]);
});

// ===== MARKET SWITCHING =====
function switchMarket(market) {
    activeMarket = market;
    watchlist = [...(WATCHLISTS[market] || WATCHLISTS.US)];
    watchlistData = {};

    // Update buttons
    document.querySelectorAll('.mkt-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.mkt-btn').forEach(b => {
        if (b.textContent.trim() === market) b.classList.add('active');
    });

    // Reset and reload
    refreshWatchlist();
    selectStock(MARKET_DEFAULTS[market] || watchlist[0]);

    // Clear sector heatmap
    document.getElementById('sector-heatmap').innerHTML = '';
    document.getElementById('market-overview').innerHTML = '';
}

// Helper: get friendly name for a symbol
function getStockName(symbol) {
    if (activeMarket === 'MY' && myStockNames[symbol]) {
        return myStockNames[symbol];
    }
    return symbol;
}

// ===== CLOCK =====
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    });
}

// ===== AUTO REFRESH =====
function setRefreshRate() {
    const rate = parseInt(document.getElementById('refresh-rate').value);
    refreshRate = rate;

    if (refreshInterval) clearInterval(refreshInterval);

    const dot = document.getElementById('refresh-dot');
    if (rate === 0) {
        dot.classList.add('paused');
        return;
    }

    dot.classList.remove('paused');
    refreshInterval = setInterval(() => {
        refreshWatchlist();
        updateMarketTicker();
    }, rate * 1000);
}

// ===== WATCHLIST =====
function addToWatchlist() {
    const input = document.getElementById('add-symbol');
    const symbol = input.value.trim().toUpperCase();
    if (symbol && !watchlist.includes(symbol)) {
        watchlist.push(symbol);
        refreshWatchlist();
    }
    input.value = '';
}

async function refreshWatchlist() {
    const symbols = watchlist.join(',');
    try {
        const res = await fetch(`/api/quotes?symbols=${symbols}`);
        const data = await res.json();
        if (data.error) return;

        const tbody = document.getElementById('watchlist-body');
        tbody.innerHTML = '';

        (data.quotes || []).forEach(q => {
            if (q.error) return;
            watchlistData[q.symbol] = q;

            const chg = q.percent_change || 0;
            const chgColor = chg >= 0 ? 'var(--green)' : 'var(--red)';
            const chgSign = chg >= 0 ? '+' : '';
            const isActive = q.symbol === activeSymbol ? 'active-row' : '';

            // Simple signal based on change
            let signal, sigClass;
            if (chg > 1) { signal = 'BUY'; sigClass = 'buy'; }
            else if (chg < -1) { signal = 'SELL'; sigClass = 'sell'; }
            else { signal = 'HOLD'; sigClass = 'hold'; }

            const displayName = getStockName(q.symbol);
            const currency = activeMarket === 'MY' ? 'RM' : '$';

            tbody.innerHTML += `
                <tr class="${isActive}" onclick="selectStock('${q.symbol}')" title="${q.symbol}">
                    <td class="w-sym">${displayName}</td>
                    <td class="w-price">${currency}${q.current_price.toFixed(2)}</td>
                    <td style="color:${chgColor}">${chgSign}${chg.toFixed(2)}%</td>
                    <td><span class="w-signal ${sigClass}">${signal}</span></td>
                </tr>
            `;
        });

        document.getElementById('watchlist-updated').textContent =
            'Updated ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

        // Update top ticker
        updateMarketTicker();
    } catch (err) {
        console.error('Watchlist error:', err);
    }
}

function updateMarketTicker() {
    const ticker = document.getElementById('market-ticker');
    const keySymbols = activeMarket === 'MY'
        ? ['1155.KL', '1295.KL', '1023.KL', '5347.KL', '5183.KL']
        : ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'];
    const currency = activeMarket === 'MY' ? 'RM' : '$';
    let html = '';

    keySymbols.forEach(sym => {
        const q = watchlistData[sym];
        if (q) {
            const chg = q.percent_change || 0;
            const color = chg >= 0 ? 'var(--green)' : 'var(--red)';
            const sign = chg >= 0 ? '+' : '';
            const name = getStockName(sym);
            html += `<span class="ticker-item">
                <span class="t-sym">${name}</span>
                <span class="t-price">${currency}${q.current_price.toFixed(2)}</span>
                <span class="t-chg" style="color:${color}">${sign}${chg.toFixed(2)}%</span>
            </span>`;
        }
    });

    ticker.innerHTML = html;
}

// ===== SELECT STOCK =====
async function selectStock(symbol) {
    activeSymbol = symbol;

    // Update header
    const q = watchlistData[symbol];
    const displayName = getStockName(symbol);
    const currency = activeMarket === 'MY' ? 'RM' : '$';
    document.getElementById('active-symbol').textContent = activeMarket === 'MY' ? `${displayName} (${symbol})` : symbol;
    if (q) {
        document.getElementById('active-price').textContent = `${currency}${q.current_price.toFixed(2)}`;
        const chg = q.percent_change || 0;
        const sign = chg >= 0 ? '+' : '';
        document.getElementById('active-change').textContent = `${sign}${chg.toFixed(2)}%`;
        document.getElementById('active-change').style.color = chg >= 0 ? 'var(--green)' : 'var(--red)';
    }

    // Highlight in watchlist
    document.querySelectorAll('.watchlist-table tr').forEach(r => r.classList.remove('active-row'));
    document.querySelectorAll('.watchlist-table tr').forEach(r => {
        if (r.querySelector('.w-sym')?.textContent === symbol) r.classList.add('active-row');
    });

    // Load chart
    loadChart(symbol, activeTimeframe);
}

function changeTimeframe(tf) {
    activeTimeframe = tf;
    document.querySelectorAll('.timeframe-btns button').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    loadChart(activeSymbol, tf);
}

async function loadChart(symbol, period) {
    try {
        const res = await fetch(`/api/history/${symbol}?period=${period}`);
        const data = await res.json();
        if (data.error) return;

        renderMainChart(symbol, data);
        renderMiniRSI(data);
        renderMiniMACD(data);
        renderMiniVolume(data);
    } catch (err) {
        console.error('Chart error:', err);
    }
}

function destroyChart(c) { if (c) c.destroy(); return null; }

function renderMainChart(symbol, data) {
    mainChart = destroyChart(mainChart);
    mainChart = new Chart(document.getElementById('main-chart'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: symbol,
                    data: data.close,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59,130,246,0.06)',
                    fill: true,
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.2,
                },
                {
                    label: 'SMA 20',
                    data: data.sma_20,
                    borderColor: '#fbbf24',
                    borderWidth: 1,
                    pointRadius: 0,
                    borderDash: [3, 2],
                },
                {
                    label: 'SMA 50',
                    data: data.sma_50,
                    borderColor: '#f97316',
                    borderWidth: 1,
                    pointRadius: 0,
                    borderDash: [3, 2],
                },
                {
                    label: 'BB Upper',
                    data: data.bb_upper,
                    borderColor: 'rgba(139,92,246,0.3)',
                    borderWidth: 1,
                    pointRadius: 0,
                },
                {
                    label: 'BB Lower',
                    data: data.bb_lower,
                    borderColor: 'rgba(139,92,246,0.3)',
                    borderWidth: 1,
                    pointRadius: 0,
                    fill: '-1',
                    backgroundColor: 'rgba(139,92,246,0.04)',
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: { display: true, grid: { display: false }, ticks: { maxTicksLimit: 10, font: { size: 9 } } },
                y: { grid: { color: '#111827' }, ticks: { font: { size: 9 } } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

function renderMiniRSI(data) {
    miniRsi = destroyChart(miniRsi);
    miniRsi = new Chart(document.getElementById('mini-rsi'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [{
                data: data.rsi,
                borderColor: '#8b5cf6',
                borderWidth: 1,
                pointRadius: 0,
                tension: 0.3,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { display: false },
                y: { display: true, min: 0, max: 100, grid: { display: false }, ticks: { font: { size: 8 }, stepSize: 30 } }
            },
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'RSI', font: { size: 9 }, padding: 2, color: '#6b7280' }
            }
        },
        plugins: [{
            id: 'rsiZones',
            beforeDraw(chart) {
                const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                ctx.fillStyle = 'rgba(255,71,87,0.05)';
                ctx.fillRect(left, y.getPixelForValue(100), right-left, y.getPixelForValue(70)-y.getPixelForValue(100));
                ctx.fillStyle = 'rgba(0,220,130,0.05)';
                ctx.fillRect(left, y.getPixelForValue(30), right-left, y.getPixelForValue(0)-y.getPixelForValue(30));
            }
        }]
    });
}

function renderMiniMACD(data) {
    const hist = data.macd.map((m, i) => (m !== null && data.signal_line[i] !== null) ? +(m - data.signal_line[i]).toFixed(4) : null);

    miniMacd = destroyChart(miniMacd);
    miniMacd = new Chart(document.getElementById('mini-macd'), {
        type: 'bar',
        data: {
            labels: data.dates,
            datasets: [{
                data: hist,
                backgroundColor: hist.map(v => v >= 0 ? 'rgba(0,220,130,0.4)' : 'rgba(255,71,87,0.4)'),
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { display: false },
                y: { display: false }
            },
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'MACD', font: { size: 9 }, padding: 2, color: '#6b7280' }
            }
        }
    });
}

function renderMiniVolume(data) {
    miniVol = destroyChart(miniVol);
    miniVol = new Chart(document.getElementById('mini-volume'), {
        type: 'bar',
        data: {
            labels: data.dates,
            datasets: [{
                data: data.volume,
                backgroundColor: data.close.map((c, i) =>
                    i > 0 && c >= data.close[i-1] ? 'rgba(0,220,130,0.3)' : 'rgba(255,71,87,0.3)'
                ),
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { display: false },
                y: { display: false }
            },
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'VOL', font: { size: 9 }, padding: 2, color: '#6b7280' }
            }
        }
    });
}

// ===== AI PREDICTION =====
async function runPrediction() {
    const btn = document.getElementById('run-predict-btn');
    btn.disabled = true;
    btn.textContent = '...';
    document.getElementById('predict-loading').classList.remove('hidden');

    try {
        const res = await fetch(`/api/predict/${activeSymbol}`);
        const data = await res.json();
        document.getElementById('predict-loading').classList.add('hidden');
        btn.disabled = false;
        btn.textContent = 'Run';

        if (data.error) throw new Error(data.error);

        // Action
        const actionEl = document.getElementById('p-action');
        actionEl.textContent = data.action;
        actionEl.className = 'pred-action ' + data.action.toLowerCase().replace(' ', '-');

        // Confidence
        document.getElementById('p-confidence').textContent = `${(data.confidence * 100).toFixed(1)}% conf`;

        // Signal bars
        const signalNames = {
            technical: { label: 'Technical', color: '#3b82f6' },
            news_sentiment: { label: 'News', color: '#8b5cf6' },
            social_sentiment: { label: 'Social', color: '#06b6d4' },
            geopolitical: { label: 'Geo', color: '#f97316' },
            market_momentum: { label: 'Momentum', color: '#fbbf24' },
        };

        const barsEl = document.getElementById('signal-bars');
        barsEl.innerHTML = '';
        for (const [key, meta] of Object.entries(signalNames)) {
            const sig = data.signals[key] || {};
            const strength = sig.strength || 0.5;
            const pct = (strength * 100).toFixed(0);
            const direction = sig.signal || 'neutral';
            const valColor = direction === 'bullish' ? 'var(--green)' : direction === 'bearish' ? 'var(--red)' : 'var(--yellow)';

            barsEl.innerHTML += `
                <div class="signal-bar-row">
                    <span class="signal-bar-label">${meta.label}</span>
                    <div class="signal-bar-track">
                        <div class="signal-bar-fill" style="width:${pct}%;background:${meta.color}"></div>
                    </div>
                    <span class="signal-bar-value" style="color:${valColor}">${pct}%</span>
                </div>
            `;
        }

        // Reasons
        const reasonsEl = document.getElementById('pred-reasons');
        reasonsEl.innerHTML = '';
        (data.reasons || []).forEach(r => {
            const match = r.match(/^\[([^\]]+)\]\s*(.*)/);
            if (match) {
                reasonsEl.innerHTML += `<div class="pred-reason"><span class="reason-src">[${match[1]}]</span>${match[2]}</div>`;
            } else {
                reasonsEl.innerHTML += `<div class="pred-reason">${r}</div>`;
            }
        });

        // Update watchlist signal for this stock
        refreshWatchlist();
    } catch (err) {
        document.getElementById('predict-loading').classList.add('hidden');
        btn.disabled = false;
        btn.textContent = 'Run';
        alert('Error: ' + err.message);
    }
}

// ===== SECTOR HEATMAP =====
async function loadSectorHeatmap() {
    document.getElementById('sector-loading').classList.remove('hidden');
    document.getElementById('sector-heatmap').innerHTML = '';

    try {
        const res = await fetch(`/api/sectors?market=${activeMarket}`);
        const data = await res.json();
        document.getElementById('sector-loading').classList.add('hidden');

        if (data.error) throw new Error(data.error);

        const heatmap = document.getElementById('sector-heatmap');
        (data.sectors || []).forEach(s => {
            const score = s.score || 0;
            // Color: green for positive, red for negative, interpolated
            let bg;
            if (score > 0) {
                const intensity = Math.min(score * 3, 1);
                bg = `rgba(0,220,130,${0.15 + intensity * 0.55})`;
            } else if (score < 0) {
                const intensity = Math.min(Math.abs(score) * 3, 1);
                bg = `rgba(255,71,87,${0.15 + intensity * 0.55})`;
            } else {
                bg = 'rgba(251,191,36,0.2)';
            }

            heatmap.innerHTML += `
                <div class="sector-tile" style="background:${bg}">
                    <div class="s-name">${s.name.replace('Consumer ', 'C.').replace('Communication ', 'Comm.')}</div>
                    <div class="s-score">${score >= 0 ? '+' : ''}${score.toFixed(3)}</div>
                    <div class="s-etf">${s.etf} | ${s.action}</div>
                </div>
            `;
        });
    } catch (err) {
        document.getElementById('sector-loading').classList.add('hidden');
        alert('Error: ' + err.message);
    }
}

// ===== MARKET OVERVIEW =====
async function loadMarketOverview() {
    document.getElementById('overview-loading').classList.remove('hidden');
    document.getElementById('market-overview').innerHTML = '';

    try {
        const res = await fetch(`/api/market-overview?market=${activeMarket}`);
        const data = await res.json();
        document.getElementById('overview-loading').classList.add('hidden');

        if (data.error) throw new Error(data.error);

        const grid = document.getElementById('market-overview');
        const currency = activeMarket === 'MY' ? 'RM' : '$';
        const labels = {
            // US
            SPY: 'S&P 500', QQQ: 'NASDAQ', DIA: 'DOW 30', IWM: 'Russell 2K',
            VXX: 'VIX', GLD: 'Gold', USO: 'Oil', SLV: 'Silver',
            'BTC-USD': 'Bitcoin', 'ETH-USD': 'Ethereum',
            TLT: '20Y Bond', SHY: '1-3Y Bond',
            XLK: 'Tech', XLF: 'Finance', XLE: 'Energy', XLV: 'Health',
            // MY
            '^KLSE': 'KLCI Index',
            '1155.KL': 'Maybank', '1295.KL': 'Public Bank', '1023.KL': 'CIMB',
            '5183.KL': 'PetChem', '5235.KL': 'Petronas Gas',
            '6947.KL': 'CelcomDigi', '6888.KL': 'Axiata',
            '5285.KL': 'Sime Darby P', '2445.KL': 'KL Kepong',
            '5347.KL': 'Tenaga', '5225.KL': 'IHH', '8869.KL': 'Press Metal',
        };

        for (const [category, quotes] of Object.entries(data.overview)) {
            quotes.forEach(q => {
                if (q.error) return;
                const chg = q.percent_change || 0;
                const color = chg >= 0 ? 'var(--green)' : 'var(--red)';
                const sign = chg >= 0 ? '+' : '';
                const label = labels[q.symbol] || getStockName(q.symbol);
                const cur = (q.symbol.includes('.KL') || q.symbol.startsWith('^KL')) ? 'RM' : '$';

                grid.innerHTML += `
                    <div class="market-card" onclick="selectStock('${q.symbol}')">
                        <div class="m-sym">${label}</div>
                        <div class="m-price">${cur}${q.current_price.toFixed(2)}</div>
                        <div class="m-chg" style="color:${color}">${sign}${chg.toFixed(2)}%</div>
                    </div>
                `;
            });
        }
    } catch (err) {
        document.getElementById('overview-loading').classList.add('hidden');
        alert('Error: ' + err.message);
    }
}

// ===== LIVE NEWS =====
async function loadLiveNews() {
    document.getElementById('news-loading').classList.remove('hidden');
    document.getElementById('news-feed').innerHTML = '';

    try {
        const res = await fetch('/api/news/fetch-all');
        const data = await res.json();
        document.getElementById('news-loading').classList.add('hidden');

        const feed = document.getElementById('news-feed');
        const articles = (data.news || []).slice(0, 50);

        articles.forEach(n => {
            const sentiment = n.sentiment_label || 'neutral';
            const platform = n.source_platform || '';
            const time = (n.fetched_at || '').slice(11, 16);
            const figure = n.related_figure ? `<span style="color:var(--cyan)">${n.related_figure}</span>` : '';

            feed.innerHTML += `
                <div class="news-item">
                    <div class="n-headline">${n.headline}</div>
                    <div class="n-meta">
                        <span class="n-time">${time}</span>
                        <span class="n-platform">${platform}</span>
                        <span class="n-sentiment ${sentiment}">${sentiment}</span>
                        ${figure}
                    </div>
                </div>
            `;
        });
    } catch (err) {
        document.getElementById('news-loading').classList.add('hidden');
        alert('Error: ' + err.message);
    }
}

// ===== FEAR & GREED INDEX =====
async function loadFearGreed() {
    document.getElementById('sector-heatmap').innerHTML = '';
    const display = document.getElementById('fear-greed-display');
    display.innerHTML = '<div class="mini-loading">Calculating...</div>';
    display.classList.remove('hidden');

    try {
        const res = await fetch(`/api/fear-greed?market=${activeMarket}`);
        const data = await res.json();

        const score = data.score || 50;
        const label = data.label || 'Neutral';
        const color = score >= 55 ? 'var(--green)' : score <= 45 ? 'var(--red)' : 'var(--yellow)';

        let html = `
            <div style="text-align:center;padding:12px">
                <div style="font-size:36px;font-weight:900;color:${color}">${score}</div>
                <div style="font-size:12px;color:${color};font-weight:700;margin-bottom:8px">${label}</div>
                <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;margin:0 10px">
                    <div style="width:${score}%;height:100%;background:linear-gradient(90deg,var(--red),var(--yellow),var(--green));border-radius:4px"></div>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:8px;color:var(--text-muted);margin:4px 10px 0">
                    <span>FEAR</span><span>GREED</span>
                </div>
            </div>
        `;

        // Components
        for (const [key, comp] of Object.entries(data.components || {})) {
            const cColor = comp.score >= 55 ? 'var(--green)' : comp.score <= 45 ? 'var(--red)' : 'var(--yellow)';
            html += `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 12px;border-top:1px solid var(--border);font-size:10px">
                    <span style="color:var(--text-muted)">${comp.label}</span>
                    <span style="color:${cColor};font-weight:700">${comp.score}</span>
                </div>
            `;
        }

        display.innerHTML = html;
    } catch (err) {
        display.innerHTML = `<div class="mini-loading">Error: ${err.message}</div>`;
    }
}

// ===== BACKTEST =====
async function runBacktest() {
    const sym = activeSymbol;
    const display = document.getElementById('backtest-display');
    const overview = document.getElementById('market-overview');
    overview.innerHTML = '';
    display.classList.remove('hidden');
    display.innerHTML = '<div class="mini-loading">Backtesting...</div>';

    try {
        const res = await fetch(`/api/backtest/${sym}?period=1y&hold_days=5`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        const alphaColor = data.alpha >= 0 ? 'var(--green)' : 'var(--red)';
        const retColor = data.total_return >= 0 ? 'var(--green)' : 'var(--red)';

        display.innerHTML = `
            <div style="padding:8px 12px">
                <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">BACKTEST: ${data.symbol} (${data.period})</div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px">
                    <div>Accuracy: <strong>${data.accuracy}%</strong></div>
                    <div>Win Rate: <strong>${data.win_rate}%</strong></div>
                    <div style="color:${retColor}">Return: <strong>${data.total_return}%</strong></div>
                    <div>Buy&Hold: <strong>${data.buy_hold_return}%</strong></div>
                    <div style="color:${alphaColor}">Alpha: <strong>${data.alpha > 0 ? '+' : ''}${data.alpha}%</strong></div>
                    <div>Sharpe: <strong>${data.sharpe_ratio}</strong></div>
                    <div>Max DD: <strong style="color:var(--red)">-${data.max_drawdown}%</strong></div>
                    <div>Trades: <strong>${data.trade_count}</strong></div>
                    <div>Avg Win: <strong style="color:var(--green)">+${data.avg_win}%</strong></div>
                    <div>Avg Loss: <strong style="color:var(--red)">${data.avg_loss}%</strong></div>
                </div>
            </div>
        `;
    } catch (err) {
        display.innerHTML = `<div class="mini-loading">Error: ${err.message}</div>`;
    }
}

// ===== CORRELATIONS =====
async function loadCorrelations() {
    const display = document.getElementById('correlation-display');
    const overview = document.getElementById('market-overview');
    overview.innerHTML = '';
    document.getElementById('backtest-display').classList.add('hidden');
    display.classList.remove('hidden');
    display.innerHTML = '<div class="mini-loading">Calculating correlations...</div>';

    const defaultSyms = activeMarket === 'MY'
        ? '1155.KL,1023.KL,5347.KL,5183.KL,5225.KL,8869.KL'
        : 'SPY,QQQ,AAPL,TSLA,GLD,TLT';

    try {
        const res = await fetch(`/api/correlations?symbols=${defaultSyms}`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        let html = '<div style="padding:8px;overflow-y:auto;max-height:200px">';
        html += '<div style="font-size:9px;color:var(--text-muted);margin-bottom:6px">CORRELATION MATRIX</div>';

        // Notable pairs
        (data.notable_pairs || []).forEach(p => {
            const color = p.correlation > 0.5 ? 'var(--green)' : p.correlation < -0.3 ? 'var(--red)' : 'var(--yellow)';
            html += `<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:10px;border-bottom:1px solid var(--border)">
                <span style="color:var(--text-dim)">${p.pair}</span>
                <span style="color:${color};font-weight:700">${p.correlation} (${p.strength})</span>
            </div>`;
        });
        html += '</div>';

        display.innerHTML = html;
    } catch (err) {
        display.innerHTML = `<div class="mini-loading">Error: ${err.message}</div>`;
    }
}

// ===== ALERTS =====
async function loadAlerts() {
    const display = document.getElementById('alerts-display');
    const newsFeed = document.getElementById('news-feed');
    const portfolio = document.getElementById('portfolio-display');
    newsFeed.innerHTML = '';
    portfolio.classList.add('hidden');
    display.classList.remove('hidden');

    try {
        // Check triggered alerts
        const checkRes = await fetch('/api/alerts/check');
        const checkData = await checkRes.json();

        const res = await fetch('/api/alerts');
        const data = await res.json();

        let html = '<div style="padding:8px">';

        // Create alert form
        html += `
            <div style="margin-bottom:8px;padding:6px;background:var(--bg);border-radius:4px">
                <div style="font-size:9px;color:var(--text-muted);margin-bottom:4px">NEW ALERT</div>
                <div style="display:flex;gap:4px;flex-wrap:wrap">
                    <input id="alert-sym" value="${activeSymbol}" style="width:60px;padding:2px 4px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:10px;border-radius:3px;font-family:inherit">
                    <select id="alert-type" style="padding:2px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:10px;border-radius:3px;font-family:inherit">
                        <option value="price">Price</option>
                        <option value="rsi">RSI</option>
                    </select>
                    <select id="alert-cond" style="padding:2px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:10px;border-radius:3px;font-family:inherit">
                        <option value="above">Above</option>
                        <option value="below">Below</option>
                    </select>
                    <input id="alert-thresh" placeholder="value" style="width:60px;padding:2px 4px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:10px;border-radius:3px;font-family:inherit">
                    <button class="btn-sm btn-accent" onclick="createAlert()">Add</button>
                </div>
            </div>
        `;

        // Triggered alerts
        if (checkData.triggered && checkData.triggered.length > 0) {
            html += '<div style="font-size:9px;color:var(--red);margin-bottom:4px;font-weight:700">TRIGGERED</div>';
            checkData.triggered.forEach(a => {
                html += `<div style="padding:4px 0;border-bottom:1px solid var(--border);font-size:10px;color:var(--red)">
                    ${a.symbol} ${a.alert_type} ${a.condition} ${a.threshold} — current: ${a.current_value}
                </div>`;
            });
        }

        // Active alerts
        html += '<div style="font-size:9px;color:var(--text-muted);margin:8px 0 4px">ACTIVE ALERTS</div>';
        (data.alerts || []).forEach(a => {
            const status = a.is_triggered ? '<span style="color:var(--red)">TRIGGERED</span>' : '<span style="color:var(--green)">ACTIVE</span>';
            html += `<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:10px;border-bottom:1px solid var(--border)">
                <span>${a.symbol} ${a.alert_type} ${a.condition} ${a.threshold}</span>
                <span>${status}</span>
            </div>`;
        });

        html += '</div>';
        display.innerHTML = html;
    } catch (err) {
        display.innerHTML = `<div class="mini-loading">Error: ${err.message}</div>`;
    }
}

async function createAlert() {
    const body = {
        symbol: document.getElementById('alert-sym').value,
        alert_type: document.getElementById('alert-type').value,
        condition: document.getElementById('alert-cond').value,
        threshold: document.getElementById('alert-thresh').value,
    };

    try {
        await fetch('/api/alerts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        loadAlerts(); // Refresh
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// ===== PORTFOLIO =====
async function loadPortfolio() {
    const display = document.getElementById('portfolio-display');
    const newsFeed = document.getElementById('news-feed');
    const alerts = document.getElementById('alerts-display');
    newsFeed.innerHTML = '';
    alerts.classList.add('hidden');
    display.classList.remove('hidden');
    display.innerHTML = '<div class="mini-loading">Loading portfolio...</div>';

    try {
        const res = await fetch('/api/portfolio/summary');
        const data = await res.json();

        const pnlColor = (data.total_pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)';
        const currency = activeMarket === 'MY' ? 'RM' : '$';

        let html = `<div style="padding:8px">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:10px;margin-bottom:8px">
                <div>Capital: <strong>${currency}${(data.initial_capital || 10000).toLocaleString()}</strong></div>
                <div>Value: <strong>${currency}${(data.total_value_with_cash || 0).toLocaleString()}</strong></div>
                <div style="color:${pnlColor}">P&L: <strong>${currency}${(data.total_pnl || 0).toFixed(2)} (${(data.overall_return_pct || 0).toFixed(1)}%)</strong></div>
                <div>Trades: <strong>${data.trade_count || 0}</strong></div>
            </div>
        `;

        // Quick trade buttons
        html += `
            <div style="padding:4px;background:var(--bg);border-radius:4px;margin-bottom:6px">
                <div style="font-size:9px;color:var(--text-muted);margin-bottom:3px">QUICK TRADE: ${activeSymbol}</div>
                <div style="display:flex;gap:4px;align-items:center">
                    <input id="trade-qty" value="10" style="width:40px;padding:2px 4px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:10px;border-radius:3px;font-family:inherit">
                    <span style="font-size:9px;color:var(--text-muted)">shares</span>
                    <button class="btn-sm" style="border-color:var(--green);color:var(--green)" onclick="quickTrade('BUY')">BUY</button>
                    <button class="btn-sm" style="border-color:var(--red);color:var(--red)" onclick="quickTrade('SELL')">SELL</button>
                </div>
            </div>
        `;

        // Holdings
        if (data.holdings && data.holdings.length > 0) {
            html += '<div style="font-size:9px;color:var(--text-muted);margin-bottom:3px">HOLDINGS</div>';
            data.holdings.forEach(h => {
                const hColor = (h.pnl || 0) >= 0 ? 'var(--green)' : 'var(--red)';
                const name = getStockName(h.symbol);
                html += `<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:10px;border-bottom:1px solid var(--border)">
                    <span>${name} x${h.quantity}</span>
                    <span style="color:${hColor}">${currency}${h.pnl.toFixed(2)} (${h.pnl_pct}%)</span>
                </div>`;
            });
        }

        html += '</div>';
        display.innerHTML = html;
    } catch (err) {
        display.innerHTML = `<div class="mini-loading">Error: ${err.message}</div>`;
    }
}

async function quickTrade(action) {
    const qty = parseInt(document.getElementById('trade-qty').value) || 10;
    const q = watchlistData[activeSymbol];
    const price = q ? q.current_price : 0;

    if (!price) { alert('No price data'); return; }

    try {
        await fetch('/api/portfolio/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: activeSymbol,
                action: action,
                quantity: qty,
                price: price,
            }),
        });
        loadPortfolio();
    } catch (err) {
        alert('Error: ' + err.message);
    }
}
