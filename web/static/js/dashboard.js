/* ===== Stock Prediction Dashboard - Frontend Logic ===== */

// Market state
let dashMarket = 'US';

function switchDashMarket(market) {
    dashMarket = market;
    document.querySelectorAll('.market-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    if (market === 'MY') {
        document.getElementById('quick-picks-us').classList.add('hidden');
        document.getElementById('quick-picks-my').classList.remove('hidden');
        document.getElementById('symbol-input').placeholder = 'Enter Bursa code (e.g., 1155.KL for Maybank)';
    } else {
        document.getElementById('quick-picks-us').classList.remove('hidden');
        document.getElementById('quick-picks-my').classList.add('hidden');
        document.getElementById('symbol-input').placeholder = 'Enter stock symbol (e.g., TSLA, AAPL, NVDA)';
    }
}

// Chart instances (for cleanup)
let priceChart, rsiChart, macdChart, volumeChart;
let signalsRadar, weightsDoughnut;
let sectorBarChart, sectorRadarChart;

// ===== TABS =====
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab).classList.add('active');
    });
});

// ===== CLOCK =====
function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}
setInterval(updateClock, 1000);
updateClock();

// ===== ENTER KEY =====
document.getElementById('symbol-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') analyzeStock();
});

// ===== HELPERS =====
function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }

function actionClass(action) {
    return action.toLowerCase().replace(' ', '-');
}

function actionColor(action) {
    const colors = {
        'STRONG BUY': '#00e676', 'BUY': '#69f0ae', 'HOLD': '#ffc107',
        'SELL': '#ff6e40', 'STRONG SELL': '#ff1744'
    };
    return colors[action] || '#ffc107';
}

function signalColor(signal) {
    if (signal === 'bullish') return '#00c853';
    if (signal === 'bearish') return '#ff1744';
    return '#ffc107';
}

function destroyChart(chart) {
    if (chart) chart.destroy();
    return null;
}

// ===== CHART DEFAULTS =====
Chart.defaults.color = '#9aa0b0';
Chart.defaults.borderColor = '#2a2e3f';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";

// ===== STOCK ANALYSIS =====
function quickAnalyze(symbol) {
    document.getElementById('symbol-input').value = symbol;
    analyzeStock();
}

async function analyzeStock() {
    const symbol = document.getElementById('symbol-input').value.trim().toUpperCase();
    if (!symbol) return;

    const period = document.getElementById('period-select').value;

    // Show loading, hide results
    show('stock-loading');
    hide('prediction-card');
    hide('signals-section');
    hide('chart-section');
    hide('reasons-section');

    try {
        // Fetch prediction and history in parallel
        const [predRes, histRes] = await Promise.all([
            fetch(`/api/predict/${symbol}`),
            fetch(`/api/history/${symbol}?period=${period}`)
        ]);

        const pred = await predRes.json();
        const hist = await histRes.json();

        if (pred.error) throw new Error(pred.error);

        hide('stock-loading');
        renderPrediction(pred);
        renderSignals(pred.signals);
        renderReasons(pred.reasons);

        if (!hist.error) {
            renderPriceChart(symbol, hist);
            renderRSIChart(hist);
            renderMACDChart(hist);
            renderVolumeChart(hist);
            show('chart-section');
        }
    } catch (err) {
        hide('stock-loading');
        alert('Error: ' + err.message);
    }
}

function renderPrediction(pred) {
    document.getElementById('pred-symbol').textContent = pred.symbol;
    document.getElementById('pred-price').textContent = `$${pred.price_current.toFixed(2)}`;

    const actionEl = document.getElementById('pred-action');
    actionEl.textContent = pred.action;
    actionEl.className = 'action-badge ' + actionClass(pred.action);

    const confPct = (pred.confidence * 100).toFixed(1);
    document.getElementById('pred-confidence-fill').style.width = confPct + '%';
    document.getElementById('pred-confidence-text').textContent = confPct + '%';

    show('prediction-card');
}

function renderSignals(signals) {
    // Radar chart
    const labels = Object.keys(signals).map(s => s.replace('_', ' ').toUpperCase());
    const strengths = Object.values(signals).map(s => s.strength || 0.5);
    const colors = Object.values(signals).map(s => signalColor(s.signal));

    signalsRadar = destroyChart(signalsRadar);
    signalsRadar = new Chart(document.getElementById('signals-radar'), {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Signal Strength',
                data: strengths,
                backgroundColor: 'rgba(41,121,255,0.15)',
                borderColor: '#2979ff',
                pointBackgroundColor: colors,
                pointRadius: 6,
                borderWidth: 2,
            }]
        },
        options: {
            scales: { r: { beginAtZero: true, max: 1, grid: { color: '#2a2e3f' }, ticks: { display: false } } },
            plugins: { legend: { display: false } }
        }
    });

    // Doughnut chart (weights)
    const weightLabels = ['Technical', 'News', 'Social', 'Geopolitical', 'Momentum'];
    const weightValues = [30, 25, 20, 15, 10];
    const weightColors = ['#2979ff', '#7c4dff', '#00e5ff', '#ff6e40', '#ffc107'];

    weightsDoughnut = destroyChart(weightsDoughnut);
    weightsDoughnut = new Chart(document.getElementById('weights-doughnut'), {
        type: 'doughnut',
        data: {
            labels: weightLabels,
            datasets: [{ data: weightValues, backgroundColor: weightColors, borderWidth: 0 }]
        },
        options: {
            cutout: '60%',
            plugins: { legend: { position: 'right', labels: { padding: 12, font: { size: 12 } } } }
        }
    });

    // Signal cards
    const grid = document.getElementById('signal-cards');
    grid.innerHTML = '';
    for (const [name, sig] of Object.entries(signals)) {
        const direction = sig.signal || 'neutral';
        const strength = (sig.strength || 0.5).toFixed(2);
        grid.innerHTML += `
            <div class="signal-card">
                <div class="signal-name">${name.replace('_', ' ')}</div>
                <div class="signal-direction ${direction}">${direction === 'bullish' ? '&#9650;' : direction === 'bearish' ? '&#9660;' : '&#9679;'} ${direction}</div>
                <div class="signal-strength">Strength: ${strength}</div>
            </div>
        `;
    }

    show('signals-section');
}

function renderReasons(reasons) {
    const list = document.getElementById('reasons-list');
    list.innerHTML = '';
    reasons.forEach(r => {
        const match = r.match(/^\[([^\]]+)\]\s*(.*)/);
        if (match) {
            list.innerHTML += `<li><span class="reason-tag">${match[1]}</span>${match[2]}</li>`;
        } else {
            list.innerHTML += `<li>${r}</li>`;
        }
    });
    show('reasons-section');
}

// ===== PRICE CHARTS =====
function renderPriceChart(symbol, data) {
    priceChart = destroyChart(priceChart);
    priceChart = new Chart(document.getElementById('price-chart'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: `${symbol} Close`,
                    data: data.close,
                    borderColor: '#2979ff',
                    backgroundColor: 'rgba(41,121,255,0.08)',
                    fill: true,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.3,
                },
                {
                    label: 'SMA 20',
                    data: data.sma_20,
                    borderColor: '#ffc107',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    borderDash: [5, 3],
                },
                {
                    label: 'SMA 50',
                    data: data.sma_50,
                    borderColor: '#ff6e40',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    borderDash: [5, 3],
                },
                {
                    label: 'BB Upper',
                    data: data.bb_upper,
                    borderColor: 'rgba(124,77,255,0.4)',
                    borderWidth: 1,
                    pointRadius: 0,
                    borderDash: [2, 2],
                },
                {
                    label: 'BB Lower',
                    data: data.bb_lower,
                    borderColor: 'rgba(124,77,255,0.4)',
                    borderWidth: 1,
                    pointRadius: 0,
                    borderDash: [2, 2],
                    fill: '-1',
                    backgroundColor: 'rgba(124,77,255,0.05)',
                },
            ]
        },
        options: {
            responsive: true,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
                y: { grid: { color: '#1e2235' } }
            },
            plugins: { legend: { labels: { padding: 16 } } }
        }
    });
}

function renderRSIChart(data) {
    rsiChart = destroyChart(rsiChart);
    rsiChart = new Chart(document.getElementById('rsi-chart'), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [{
                label: 'RSI',
                data: data.rsi,
                borderColor: '#7c4dff',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.3,
                fill: false,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                y: {
                    min: 0, max: 100,
                    grid: { color: '#1e2235' },
                }
            },
            plugins: {
                legend: { display: false },
                annotation: {}  // RSI zones shown via background
            }
        },
        plugins: [{
            id: 'rsiZones',
            beforeDraw(chart) {
                const { ctx, chartArea: { left, right, top, bottom }, scales: { y } } = chart;
                // Overbought zone (70-100)
                ctx.fillStyle = 'rgba(255,23,68,0.07)';
                ctx.fillRect(left, y.getPixelForValue(100), right - left, y.getPixelForValue(70) - y.getPixelForValue(100));
                // Oversold zone (0-30)
                ctx.fillStyle = 'rgba(0,200,83,0.07)';
                ctx.fillRect(left, y.getPixelForValue(30), right - left, y.getPixelForValue(0) - y.getPixelForValue(30));
                // Lines at 30 and 70
                ctx.strokeStyle = '#444';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 4]);
                [30, 70].forEach(val => {
                    const yPos = y.getPixelForValue(val);
                    ctx.beginPath();
                    ctx.moveTo(left, yPos);
                    ctx.lineTo(right, yPos);
                    ctx.stroke();
                });
                ctx.setLineDash([]);
            }
        }]
    });
}

function renderMACDChart(data) {
    // MACD histogram
    const histogram = data.macd.map((m, i) => {
        const s = data.signal_line[i];
        return (m !== null && s !== null) ? +(m - s).toFixed(4) : null;
    });

    macdChart = destroyChart(macdChart);
    macdChart = new Chart(document.getElementById('macd-chart'), {
        type: 'bar',
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: 'Histogram',
                    data: histogram,
                    backgroundColor: histogram.map(v => v >= 0 ? 'rgba(0,200,83,0.5)' : 'rgba(255,23,68,0.5)'),
                    borderWidth: 0,
                    barPercentage: 0.8,
                    order: 2,
                },
                {
                    label: 'MACD',
                    data: data.macd,
                    type: 'line',
                    borderColor: '#2979ff',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3,
                    order: 1,
                },
                {
                    label: 'Signal',
                    data: data.signal_line,
                    type: 'line',
                    borderColor: '#ff6e40',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.3,
                    order: 1,
                },
            ]
        },
        options: {
            responsive: true,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                y: { grid: { color: '#1e2235' } }
            },
            plugins: { legend: { labels: { padding: 12 } } }
        }
    });
}

function renderVolumeChart(data) {
    volumeChart = destroyChart(volumeChart);
    volumeChart = new Chart(document.getElementById('volume-chart'), {
        type: 'bar',
        data: {
            labels: data.dates,
            datasets: [{
                label: 'Volume',
                data: data.volume,
                backgroundColor: data.close.map((c, i) =>
                    i > 0 && c >= data.close[i - 1] ? 'rgba(0,200,83,0.3)' : 'rgba(255,23,68,0.3)'
                ),
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
                y: { grid: { color: '#1e2235' }, ticks: { callback: v => (v / 1e6).toFixed(0) + 'M' } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

// ===== SECTOR ANALYSIS =====
async function loadSectors() {
    show('sector-loading');
    hide('sector-heatmap');

    try {
        const res = await fetch(`/api/sectors?market=${dashMarket}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        hide('sector-loading');
        renderSectors(data.sectors, data.market);
        show('sector-heatmap');
    } catch (err) {
        hide('sector-loading');
        alert('Error: ' + err.message);
    }
}

function renderSectors(sectors) {
    // Bar chart
    const labels = sectors.map(s => s.name);
    const scores = sectors.map(s => s.score);
    const colors = scores.map(s => s > 0.15 ? '#00c853' : s < -0.15 ? '#ff1744' : '#ffc107');

    sectorBarChart = destroyChart(sectorBarChart);
    sectorBarChart = new Chart(document.getElementById('sector-bar-chart'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Sector Score',
                data: scores,
                backgroundColor: colors,
                borderRadius: 6,
                borderWidth: 0,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            scales: {
                x: { grid: { color: '#1e2235' }, min: -1, max: 1 },
                y: { grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });

    // Radar comparison (top 5 sectors)
    const top5 = sectors.slice(0, 5);
    const radarLabels = ['Technical', 'News', 'Social', 'Geopolitical', 'Momentum'];
    const radarColors = ['#2979ff', '#00e5ff', '#7c4dff', '#ffc107', '#ff6e40'];

    sectorRadarChart = destroyChart(sectorRadarChart);
    sectorRadarChart = new Chart(document.getElementById('sector-radar-chart'), {
        type: 'radar',
        data: {
            labels: radarLabels,
            datasets: top5.map((s, i) => ({
                label: s.name,
                data: [
                    s.signal_breakdown.technical?.strength || 0.5,
                    s.signal_breakdown.news_sentiment?.strength || 0.5,
                    s.signal_breakdown.social_sentiment?.strength || 0.5,
                    s.signal_breakdown.geopolitical?.strength || 0.5,
                    s.signal_breakdown.market_momentum?.strength || 0.5,
                ],
                borderColor: radarColors[i],
                backgroundColor: radarColors[i] + '15',
                borderWidth: 2,
                pointRadius: 3,
            }))
        },
        options: {
            scales: { r: { beginAtZero: true, max: 1, grid: { color: '#2a2e3f' }, ticks: { display: false } } },
            plugins: { legend: { position: 'bottom', labels: { padding: 16 } } }
        }
    });

    // Sector cards grid
    const grid = document.getElementById('sector-grid');
    grid.innerHTML = '';
    sectors.forEach(s => {
        const ac = actionClass(s.action);
        const acColor = actionColor(s.action);
        const scoreDisplay = s.score >= 0 ? `+${s.score.toFixed(3)}` : s.score.toFixed(3);
        const scoreColor = s.score > 0 ? '#00c853' : s.score < 0 ? '#ff1744' : '#ffc107';

        grid.innerHTML += `
            <div class="sector-card" style="border-left: 4px solid ${acColor}">
                <div class="sector-name">
                    ${s.name}
                    <span class="sector-score" style="color:${scoreColor}">${scoreDisplay}</span>
                </div>
                <div class="sector-desc">${s.description}</div>
                <span class="sector-action" style="background:${acColor};color:#000">${s.action}</span>
                <span class="sector-etf">ETF: ${s.etf} &bull; Confidence: ${(s.confidence * 100).toFixed(0)}%</span>
                <div class="sector-symbols">
                    ${s.symbols.map(sym => `<span>${sym}</span>`).join('')}
                </div>
            </div>
        `;
    });
}

// ===== NEWS & GEOPOLITICAL =====
async function loadNews() {
    show('news-loading');
    document.getElementById('news-feed').innerHTML = '';

    try {
        const res = await fetch('/api/news');
        const data = await res.json();
        hide('news-loading');

        if (data.error) {
            document.getElementById('news-feed').innerHTML = `<p class="hint">${data.error}</p>`;
            return;
        }

        const feed = document.getElementById('news-feed');
        (data.articles || []).forEach(a => {
            const s = a.sentiment || {};
            feed.innerHTML += `
                <div class="news-item">
                    <div class="news-headline">
                        ${a.headline}
                        <span class="sentiment-badge ${s.label}">${s.label} (${(s.score >= 0 ? '+' : '') + (s.score || 0).toFixed(3)})</span>
                    </div>
                    <div class="news-meta">${a.source} &bull; ${a.datetime}</div>
                </div>
            `;
        });
    } catch (err) {
        hide('news-loading');
        document.getElementById('news-feed').innerHTML = `<p class="hint">Error: ${err.message}</p>`;
    }
}

async function loadGeopolitical() {
    show('geo-loading');
    document.getElementById('geo-signal').innerHTML = '';
    document.getElementById('geo-events').innerHTML = '';

    try {
        const res = await fetch('/api/geopolitical');
        const data = await res.json();
        hide('geo-loading');

        const color = data.signal === 'bullish' ? '#00c853' : data.signal === 'bearish' ? '#ff1744' : '#ffc107';
        const bg = data.signal === 'bullish' ? 'rgba(0,200,83,0.1)' : data.signal === 'bearish' ? 'rgba(255,23,68,0.1)' : 'rgba(255,193,7,0.1)';

        document.getElementById('geo-signal').innerHTML = `
            <div class="geo-signal-box" style="background:${bg}; border: 1px solid ${color}">
                <div class="geo-signal-label" style="color:${color}">${(data.signal || 'neutral').toUpperCase()}</div>
                <div style="color:var(--text-secondary); font-size:0.85rem; margin-top:4px">
                    ${data.event_count || 0} events &bull; Avg tone: ${(data.avg_tone || 0).toFixed(3)}
                </div>
            </div>
        `;

        const events = document.getElementById('geo-events');
        if (data.keyword_breakdown) {
            events.innerHTML += '<p style="margin:12px 0 8px; color:var(--text-muted); font-size:0.8rem; text-transform:uppercase">Event Breakdown</p>';
            for (const [kw, count] of Object.entries(data.keyword_breakdown)) {
                events.innerHTML += `<div class="geo-event-item">${kw}: <strong>${count}</strong> events</div>`;
            }
        }

        if (data.reasons) {
            events.innerHTML += '<p style="margin:16px 0 8px; color:var(--text-muted); font-size:0.8rem; text-transform:uppercase">Key Events</p>';
            data.reasons.forEach(r => {
                events.innerHTML += `<div class="geo-event-item">${r}</div>`;
            });
        }
    } catch (err) {
        hide('geo-loading');
        document.getElementById('geo-signal').innerHTML = `<p class="hint">Error: ${err.message}</p>`;
    }
}

// ===== NEWS HUB =====
let allNewsData = [];
let platformPieChart, sentimentPieChart;

async function fetchAllNews() {
    show('newshub-loading');
    hide('newshub-stats');
    hide('newshub-filter');
    hide('newshub-list');

    try {
        const res = await fetch('/api/news/fetch-all');
        const data = await res.json();
        hide('newshub-loading');

        if (data.error) throw new Error(data.error);

        allNewsData = data.news || [];
        renderNewsHub(data.news, data.stats, data.new_articles_saved);
    } catch (err) {
        hide('newshub-loading');
        alert('Error: ' + err.message);
    }
}

async function loadStoredNews() {
    show('newshub-loading');
    hide('newshub-stats');
    hide('newshub-filter');
    hide('newshub-list');

    try {
        const res = await fetch('/api/news/all');
        const data = await res.json();
        hide('newshub-loading');

        allNewsData = data.news || [];
        renderNewsHub(data.news, data.stats);
    } catch (err) {
        hide('newshub-loading');
        alert('Error: ' + err.message);
    }
}

function renderNewsHub(news, stats, newCount) {
    // Stats cards
    document.getElementById('stat-total').textContent = stats.total || 0;

    const platforms = stats.by_platform || {};
    document.getElementById('stat-platforms').textContent = Object.keys(platforms).length;

    const sentiments = stats.by_sentiment || {};
    const posCount = sentiments.positive || 0;
    const negCount = sentiments.negative || 0;
    const total = posCount + negCount + (sentiments.neutral || 0);
    if (total > 0) {
        const ratio = ((posCount / total) * 100).toFixed(0);
        document.getElementById('stat-sentiment').innerHTML =
            `<span style="color:#00c853">${ratio}%</span> positive`;
    }

    // Platform pie chart
    platformPieChart = destroyChart(platformPieChart);
    const platLabels = Object.keys(platforms);
    const platValues = Object.values(platforms);
    const platColors = { finnhub: '#2979ff', 'finnhub-figures': '#7c4dff', gdelt: '#ff6e40', reddit: '#ff4500' };

    platformPieChart = new Chart(document.getElementById('platform-pie-chart'), {
        type: 'doughnut',
        data: {
            labels: platLabels.map(l => l.toUpperCase()),
            datasets: [{
                data: platValues,
                backgroundColor: platLabels.map(l => platColors[l] || '#ffc107'),
                borderWidth: 0,
            }]
        },
        options: { cutout: '55%', plugins: { legend: { position: 'right' } } }
    });

    // Sentiment pie chart
    sentimentPieChart = destroyChart(sentimentPieChart);
    sentimentPieChart = new Chart(document.getElementById('sentiment-pie-chart'), {
        type: 'doughnut',
        data: {
            labels: ['Positive', 'Negative', 'Neutral'],
            datasets: [{
                data: [sentiments.positive || 0, sentiments.negative || 0, sentiments.neutral || 0],
                backgroundColor: ['#00c853', '#ff1744', '#ffc107'],
                borderWidth: 0,
            }]
        },
        options: { cutout: '55%', plugins: { legend: { position: 'right' } } }
    });

    show('newshub-stats');
    show('newshub-filter');

    // Render articles
    renderNewsArticles(news);
}

function renderNewsArticles(news) {
    const container = document.getElementById('newshub-articles');
    container.innerHTML = '';
    document.getElementById('newshub-count').textContent = `(${news.length} articles)`;

    news.forEach(n => {
        const platform = n.source_platform || 'unknown';
        const sentiment = n.sentiment_label || 'neutral';
        const score = n.sentiment_score || 0;
        const figure = n.related_figure ? `<span class="figure-tag">${n.related_figure}</span>` : '';
        const symbol = n.related_symbol ? `<span class="reason-tag">${n.related_symbol}</span>` : '';

        container.innerHTML += `
            <div class="newshub-article" data-platform="${platform}">
                <div class="article-headline">${n.headline}</div>
                <div class="article-meta">
                    <span class="platform-tag ${platform}">${platform}</span>
                    <span class="sentiment-badge ${sentiment}">${sentiment} (${score >= 0 ? '+' : ''}${score.toFixed(3)})</span>
                    ${figure}${symbol}
                    <span>${n.source_name || ''}</span>
                    <span>${n.fetched_at || ''}</span>
                </div>
            </div>
        `;
    });

    show('newshub-list');
}

function filterNews(platform) {
    // Update active filter button
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    if (platform === 'all') {
        renderNewsArticles(allNewsData);
    } else {
        const filtered = allNewsData.filter(n => n.source_platform === platform);
        renderNewsArticles(filtered);
    }
}

// ===== PREDICTION TRENDS =====
let trendScoreChart, trendConfidenceChart, trendPriceChart, sectorTrendChart;

document.getElementById('trend-symbol-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') loadTrend();
});

async function loadTrend() {
    const symbol = document.getElementById('trend-symbol-input').value.trim().toUpperCase();
    if (!symbol) return;

    const days = document.getElementById('trend-days-select').value;
    show('trends-loading');
    hide('trend-chart-section');

    try {
        const res = await fetch(`/api/predictions/trend/${symbol}?days=${days}`);
        const data = await res.json();
        hide('trends-loading');

        if (!data.trend || data.trend.length === 0) {
            alert(`No prediction history for ${symbol}. Run some predictions first!`);
            return;
        }

        renderTrendCharts(symbol, data.trend);
        show('trend-chart-section');
    } catch (err) {
        hide('trends-loading');
        alert('Error: ' + err.message);
    }

    // Also load tracked symbols
    loadTrackedSymbols();
}

function renderTrendCharts(symbol, trend) {
    document.getElementById('trend-chart-symbol').textContent = symbol;

    const labels = trend.map(t => t.created_at.replace('T', ' ').slice(0, 16));
    const scores = trend.map(t => t.score);
    const confidences = trend.map(t => t.confidence);
    const prices = trend.map(t => t.price);
    const actions = trend.map(t => t.action);

    // Score trend
    trendScoreChart = destroyChart(trendScoreChart);
    trendScoreChart = new Chart(document.getElementById('trend-score-chart'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Prediction Score',
                data: scores,
                borderColor: '#2979ff',
                backgroundColor: 'rgba(41,121,255,0.1)',
                fill: true,
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: scores.map(s =>
                    s > 0.15 ? '#00c853' : s < -0.15 ? '#ff1744' : '#ffc107'
                ),
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: '#1e2235' }, min: -1, max: 1 }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        afterLabel: (ctx) => `Action: ${actions[ctx.dataIndex]}`
                    }
                }
            }
        },
        plugins: [{
            id: 'zeroLine',
            beforeDraw(chart) {
                const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                const yPos = y.getPixelForValue(0);
                ctx.strokeStyle = '#444';
                ctx.lineWidth = 1;
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.moveTo(left, yPos);
                ctx.lineTo(right, yPos);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }]
    });

    // Confidence trend
    trendConfidenceChart = destroyChart(trendConfidenceChart);
    trendConfidenceChart = new Chart(document.getElementById('trend-confidence-chart'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Confidence',
                data: confidences,
                borderColor: '#7c4dff',
                backgroundColor: 'rgba(124,77,255,0.1)',
                fill: true,
                borderWidth: 2,
                pointRadius: 3,
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: { grid: { display: false } },
                y: { grid: { color: '#1e2235' }, min: 0, max: 1 }
            }
        }
    });

    // Price vs prediction
    trendPriceChart = destroyChart(trendPriceChart);
    trendPriceChart = new Chart(document.getElementById('trend-price-chart'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Price ($)',
                    data: prices,
                    borderColor: '#00e5ff',
                    borderWidth: 2,
                    pointRadius: 3,
                    tension: 0.3,
                    yAxisID: 'y',
                },
                {
                    label: 'Score',
                    data: scores,
                    borderColor: '#ff6e40',
                    borderWidth: 2,
                    borderDash: [5, 3],
                    pointRadius: 3,
                    tension: 0.3,
                    yAxisID: 'y1',
                }
            ]
        },
        options: {
            responsive: true,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: { grid: { display: false } },
                y: { type: 'linear', position: 'left', grid: { color: '#1e2235' },
                     title: { display: true, text: 'Price ($)', color: '#00e5ff' } },
                y1: { type: 'linear', position: 'right', min: -1, max: 1,
                      grid: { drawOnChartArea: false },
                      title: { display: true, text: 'Score', color: '#ff6e40' } },
            }
        }
    });
}

async function loadTrackedSymbols() {
    try {
        const res = await fetch('/api/predictions/symbols');
        const data = await res.json();

        if (data.symbols && data.symbols.length > 0) {
            const list = document.getElementById('tracked-symbols-list');
            list.innerHTML = '<span>Tracked:</span>';
            data.symbols.forEach(s => {
                list.innerHTML += `<button onclick="quickTrend('${s.symbol}')">${s.symbol} (${s.count})</button>`;
            });
            show('tracked-symbols');
        }
    } catch (err) {
        // Silently fail
    }
}

function quickTrend(symbol) {
    document.getElementById('trend-symbol-input').value = symbol;
    loadTrend();
}

async function loadPredictionHistory() {
    show('trends-loading');
    hide('history-section');

    try {
        const res = await fetch('/api/predictions/history?limit=200');
        const data = await res.json();
        hide('trends-loading');

        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';

        (data.predictions || []).forEach(p => {
            const acColor = actionColor(p.action);
            tbody.innerHTML += `
                <tr>
                    <td>${(p.created_at || '').replace('T', ' ').slice(0, 19)}</td>
                    <td><strong>${p.symbol}</strong></td>
                    <td><span class="table-action" style="background:${acColor};color:#000">${p.action}</span></td>
                    <td>${((p.confidence || 0) * 100).toFixed(1)}%</td>
                    <td>$${(p.price || 0).toFixed(2)}</td>
                    <td style="color:${p.score > 0 ? '#00c853' : p.score < 0 ? '#ff1744' : '#ffc107'}">
                        ${p.score >= 0 ? '+' : ''}${(p.score || 0).toFixed(3)}
                    </td>
                </tr>
            `;
        });

        show('history-section');
        loadTrackedSymbols();
    } catch (err) {
        hide('trends-loading');
        alert('Error: ' + err.message);
    }
}

async function loadSectorHistory() {
    show('sector-trend-loading');
    hide('sector-history-section');

    try {
        const res = await fetch('/api/sectors/history');
        const data = await res.json();
        hide('sector-trend-loading');

        const history = data.history || [];
        if (history.length === 0) {
            alert('No sector history yet. Run sector analysis first!');
            return;
        }

        // Group by sector
        const bySector = {};
        history.forEach(h => {
            if (!bySector[h.sector_name]) bySector[h.sector_name] = [];
            bySector[h.sector_name].push(h);
        });

        const sectorColors = [
            '#2979ff', '#00e5ff', '#7c4dff', '#ffc107', '#ff6e40',
            '#00c853', '#ff1744', '#e040fb', '#18ffff', '#ffab40', '#69f0ae'
        ];

        const datasets = Object.entries(bySector).map(([name, entries], i) => ({
            label: name,
            data: entries.map(e => ({ x: e.created_at, y: e.score })),
            borderColor: sectorColors[i % sectorColors.length],
            borderWidth: 2,
            pointRadius: 3,
            tension: 0.3,
            fill: false,
        }));

        sectorTrendChart = destroyChart(sectorTrendChart);
        sectorTrendChart = new Chart(document.getElementById('sector-trend-chart'), {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                scales: {
                    x: { type: 'category', grid: { display: false } },
                    y: { grid: { color: '#1e2235' }, min: -1, max: 1 }
                },
                plugins: { legend: { position: 'bottom', labels: { padding: 12 } } }
            }
        });

        show('sector-history-section');
    } catch (err) {
        hide('sector-trend-loading');
        alert('Error: ' + err.message);
    }
}
