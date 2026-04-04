/* ===== Pro Dashboard - Bloomberg Terminal Style ===== */

// ===== STATE =====
let activeSymbol = 'SPY';
let activeTimeframe = '6mo';
let watchlist = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'JPM'];
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
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    refreshWatchlist();
    setRefreshRate();
    selectStock('SPY');
});

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

            tbody.innerHTML += `
                <tr class="${isActive}" onclick="selectStock('${q.symbol}')">
                    <td class="w-sym">${q.symbol}</td>
                    <td class="w-price">$${q.current_price.toFixed(2)}</td>
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
    const keySymbols = ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA'];
    let html = '';

    keySymbols.forEach(sym => {
        const q = watchlistData[sym];
        if (q) {
            const chg = q.percent_change || 0;
            const color = chg >= 0 ? 'var(--green)' : 'var(--red)';
            const sign = chg >= 0 ? '+' : '';
            html += `<span class="ticker-item">
                <span class="t-sym">${sym}</span>
                <span class="t-price">$${q.current_price.toFixed(2)}</span>
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
    document.getElementById('active-symbol').textContent = symbol;
    if (q) {
        document.getElementById('active-price').textContent = `$${q.current_price.toFixed(2)}`;
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
        const res = await fetch('/api/sectors');
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
        const res = await fetch('/api/market-overview');
        const data = await res.json();
        document.getElementById('overview-loading').classList.add('hidden');

        if (data.error) throw new Error(data.error);

        const grid = document.getElementById('market-overview');
        const labels = {
            SPY: 'S&P 500', QQQ: 'NASDAQ', DIA: 'DOW 30', IWM: 'Russell 2K',
            VXX: 'VIX', GLD: 'Gold', USO: 'Oil', SLV: 'Silver',
            'BTC-USD': 'Bitcoin', 'ETH-USD': 'Ethereum',
            TLT: '20Y Bond', SHY: '1-3Y Bond',
            XLK: 'Tech', XLF: 'Finance', XLE: 'Energy', XLV: 'Health',
        };

        for (const [category, quotes] of Object.entries(data.overview)) {
            quotes.forEach(q => {
                if (q.error) return;
                const chg = q.percent_change || 0;
                const color = chg >= 0 ? 'var(--green)' : 'var(--red)';
                const sign = chg >= 0 ? '+' : '';
                const label = labels[q.symbol] || q.symbol;

                grid.innerHTML += `
                    <div class="market-card" onclick="selectStock('${q.symbol}')">
                        <div class="m-sym">${label}</div>
                        <div class="m-price">$${q.current_price.toFixed(2)}</div>
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
