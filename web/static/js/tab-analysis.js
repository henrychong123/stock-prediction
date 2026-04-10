/* ===== tab-analysis.js — Stock Analysis tab ===== */

(function () {
    let _analyzing = false; // debounce guard
    let _lastHist = null;   // stored for overlay re-renders
    let _lastSymbol = null;
    let _lastSignals = null;  // stored for signal chart re-renders
    let _lastWeightsData = null; // stored for weights doughnut re-render

    function switchMarket(market) {
        App.state.market = market;
        document.querySelectorAll('.market-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.market === market);
        });
        const input = App.$('symbol-input');
        if (market === 'MY') {
            App.hide('quick-picks-us');
            App.show('quick-picks-my');
            input.placeholder = 'Enter Bursa code (e.g., 1155.KL for Maybank)';
        } else {
            App.show('quick-picks-us');
            App.hide('quick-picks-my');
            input.placeholder = 'Enter stock symbol (e.g., TSLA, AAPL, NVDA)';
        }
    }

    function quickAnalyze(symbol) {
        // Show clean display in input (strip .KL for Bursa)
        App.$('symbol-input').value = symbol.replace('.KL', '');
        analyze();
    }

    async function analyze() {
        if (_analyzing) return;
        let symbol = App.$('symbol-input').value.trim().toUpperCase();
        if (!symbol) return;

        // Resolve Bursa input — keep display clean, resolve internally
        if (App.state.market === 'MY' && !symbol.endsWith('.KL') && !symbol.startsWith('^')) {
            if (/^\d+$/.test(symbol)) {
                // Pure digits (e.g. "1155") → append .KL internally only
                symbol = symbol + '.KL';
            } else {
                // Name alias (e.g. "INARI") → resolve via API
                try {
                    const d = await App.api(`/api/resolve-symbol?q=${encodeURIComponent(symbol)}`);
                    symbol = d.resolved;
                } catch {
                    symbol += '.KL';
                }
            }
            // Don't overwrite the input — keep what the user typed
        }

        const period = App.$('period-select').value;
        const btn = App.$('analyze-btn');

        // Debounce — disable button during fetch
        _analyzing = true;
        btn.disabled = true;
        btn.textContent = 'Analyzing\u2026';

        const isFullMode = App.$('full-mode-toggle')?.value === 'full';

        App.hide('analysis-welcome');
        App.hide('prediction-card');
        App.hide('signals-section');
        App.hide('chart-section');
        App.hide('reasons-section');
        App.hide('market-movers-card');

        // Show progress steps
        App.show('stock-loading');
        const stepsEl = App.$('analysis-steps');
        const statusText = App.$('analysis-status-text');

        const steps = [
            { id: 'price', label: 'Price Data' },
            { id: 'technical', label: 'Technical' },
            { id: 'ml', label: 'ML Model' },
        ];
        if (isFullMode) {
            steps.push(
                { id: 'news', label: 'News' },
                { id: 'social', label: 'Social' },
                { id: 'geo', label: 'Geopolitical' },
                { id: 'figures', label: 'Figures' },
            );
        }

        stepsEl.innerHTML = '';
        steps.forEach(s => {
            const el = document.createElement('span');
            el.className = 'analysis-step';
            el.id = `step-${s.id}`;
            el.innerHTML = `<span class="analysis-step-icon">\u25CB</span> ${s.label}`;
            stepsEl.appendChild(el);
        });

        function setStep(id, state) {
            const el = App.$(`step-${id}`);
            if (!el) return;
            el.className = `analysis-step ${state}`;
            const icon = state === 'done' ? '\u2713' : state === 'running' ? '\u25CF' : state === 'skipped' ? '\u2212' : '\u25CB';
            el.querySelector('.analysis-step-icon').textContent = icon;
        }

        function setStatus(msg) {
            if (statusText) statusText.textContent = msg;
        }

        try {
            // ── All modes: fetch chart data + fast prediction in parallel ──
            setStep('price', 'running');
            setStep('technical', 'running');
            setStep('ml', 'running');
            setStatus('Fetching price data & running prediction...');

            const histPromise = App.apiSilent(`/api/history/${symbol}?period=${period}`);
            // Always use fast mode for the initial prediction (returns in ~3-5s)
            // Full mode signals are fetched separately below with live progress steps
            const predPromise = App.api(`/api/predict/${symbol}?mode=fast`);

            // Chart data usually arrives first — render immediately
            const hist = await histPromise;
            setStep('price', 'done');

            if (hist && !hist.error) {
                _lastHist = hist;
                _lastSymbol = symbol;
                setStatus('Rendering charts...');
                renderPriceChart(symbol, hist);
                renderRSIChart(hist);
                renderMACDChart(hist);
                renderVolumeChart(hist);
                renderStochChart(hist);
                renderWilliamsChart(hist);
                renderCCIChart(hist);
                renderMACDHistChart(hist);
                renderADXChart(hist);
                renderOBVChart(hist);
                renderATRChart(hist);
                App.show('chart-section');
            }

            // Fast prediction completes
            setStatus('Completing prediction...');
            const pred = await predPromise;
            setStep('technical', 'done');
            setStep('ml', pred.signals?.ml_model ? 'done' : 'skipped');

            // Show prediction immediately (fast signals)
            renderPrediction(pred);
            renderSignals(pred.signals);
            renderReasons(pred.reasons);

            // ── Full mode: fetch slow signals SEPARATELY with live progress ──
            if (isFullMode) {
                setStatus('Fetching additional signals...');

                // Fire all slow signals in parallel — each updates its step on completion
                const slowSignals = {};

                function slowFetch(stepId, url, signalKey) {
                    setStep(stepId, 'running');
                    return Promise.race([
                        App.apiSilent(url).then(d => {
                            setStep(stepId, 'done');
                            if (d?.signal && signalKey) slowSignals[signalKey] = d.signal;
                        }),
                        new Promise(r => setTimeout(r, 30000)),  // 30s per-step timeout
                    ]).then(() => {
                        // If not done after timeout, mark skipped
                        const el = App.$(`step-${stepId}`);
                        if (el && !el.classList.contains('done')) setStep(stepId, 'skipped');
                    });
                }

                await Promise.allSettled([
                    slowFetch('news', `/api/signal/news/${symbol}`, 'news_sentiment'),
                    slowFetch('social', `/api/signal/social/${symbol}`, 'social_sentiment'),
                    slowFetch('geo', '/api/signal/geopolitical', 'geopolitical'),
                    slowFetch('figures', `/api/market-movers?symbol=${symbol}`, null),
                ]);

                // Merge slow signals into prediction and re-render
                if (Object.keys(slowSignals).length > 0) {
                    Object.assign(pred.signals, slowSignals);
                    renderSignals(pred.signals);
                    renderReasons(pred.reasons);
                    setStatus('Full analysis complete');
                }
            }

            App.hide('stock-loading');

            // Force Chart.js to resize to actual container dimensions
            // (fixes charts rendering at wrong width on initial load)
            requestAnimationFrame(() => {
                Object.values(App.state.charts).forEach(c => { if (c?.resize) c.resize(); });
            });

            // Load extras asynchronously
            loadFundamentals(symbol);
            loadEarnings(symbol);
            if (!isFullMode) loadMarketMovers(symbol);
        } catch (err) {
            App.hide('stock-loading');
            App.toast(err.message, 'error');
        } finally {
            _analyzing = false;
            btn.disabled = false;
            btn.textContent = 'Analyze';
        }
    }

    // ── Prediction Card ──────────────────────────────────────────────────────

    function renderPrediction(pred) {
        const isMY = pred.symbol.endsWith('.KL');
        const currency = isMY ? 'MYR' : '$';

        App.setText('pred-symbol', pred.symbol);
        App.setText('pred-price', `${currency} ${pred.price_current.toFixed(isMY ? 3 : 2)}`);
        App.setText('pred-company-name', '');

        const actionEl = App.$('pred-action');
        actionEl.textContent = pred.action;
        actionEl.className = 'action-badge action-badge-lg ' + App.actionClass(pred.action);

        const predCard = App.$('prediction-card');
        predCard.className = 'card prediction-card ' + App.actionClass(pred.action);

        const confPct = (pred.confidence * 100).toFixed(1);
        const confNum = pred.confidence * 100;
        App.$('pred-confidence-fill').style.width = confPct + '%';
        App.setText('pred-confidence-text', confPct + '%');

        // Confidence level badge
        const confBadge = App.$('pred-conf-level');
        let confClass, confLabel;
        if (confNum < 30)      { confClass = 'conf-low';  confLabel = 'Weak signal'; }
        else if (confNum < 60) { confClass = 'conf-mid';  confLabel = 'Moderate signal'; }
        else                   { confClass = 'conf-high'; confLabel = 'Strong signal'; }
        confBadge.textContent = confLabel;
        confBadge.className = `conf-level-badge ${confClass}`;
        App.$('pred-confidence-fill').className = `confidence-fill ${confClass}`;

        // Narrative
        App.setText('pred-narrative', buildNarrative(pred));
        App.show('prediction-card');

        // Weight source / cache badge
        const wsBadge = App.$('weight-source-badge');
        if (wsBadge) {
            if (pred.cached) {
                const age = pred.cached_age_min;
                const ageStr = age < 1 ? '<1 min ago' : `${Math.round(age)} min ago`;
                wsBadge.textContent = `Cached \u00B7 ${ageStr}`;
                wsBadge.className = 'weight-source-badge cached';
            } else if (pred.weight_source === 'ai_optimized') {
                wsBadge.textContent = 'AI-Optimized \u00B7 Live';
                wsBadge.className = 'weight-source-badge ai-optimized';
            } else {
                wsBadge.textContent = 'Default Weights \u00B7 Live';
                wsBadge.className = 'weight-source-badge default';
            }
        }

        // Fetch company name asynchronously
        const nameEndpoint = isMY ? `/api/bursa/quote/${pred.symbol}` : `/api/names?symbols=${pred.symbol}`;
        App.apiSilent(nameEndpoint).then(d => {
            if (!d) return;
            const name = isMY ? d.name : d[pred.symbol];
            if (name) App.setText('pred-company-name', name);
        });
    }

    function buildNarrative(pred) {
        const conf = pred.confidence * 100;
        const action = (pred.action || '').toUpperCase();
        const signals = pred.signals || {};
        const tech = signals.technical;
        const news = signals.news_sentiment;
        const momentum = signals.market_momentum;

        if (conf < 30) {
            return `Signals are mixed or insufficient to form a strong view on ${pred.symbol}. Consider waiting for a clearer setup before acting.`;
        }

        const techDir = tech?.signal || 'neutral';
        const newsDir = news?.signal || 'neutral';
        const momentumDir = momentum?.signal || 'neutral';

        const parts = [];
        if (techDir !== 'neutral')     parts.push(`Technical indicators are ${techDir}`);
        if (newsDir !== 'neutral')     parts.push(`news sentiment is ${newsDir}`);
        if (momentumDir !== 'neutral') parts.push(`market momentum is ${momentumDir}`);

        if (!parts.length) return `Signals point to a ${action} with moderate confidence. Monitor for further confirmation.`;

        const summary = parts.join(', ') + '.';

        if (action === 'STRONG BUY' || action === 'BUY')
            return `${summary} The weight of evidence suggests upside potential \u2014 but confirm with your own research before acting.`;
        if (action === 'STRONG SELL' || action === 'SELL')
            return `${summary} Combined signals indicate downside risk. This does not guarantee a decline \u2014 use as one input among many.`;
        return `${summary} No clear directional edge at this time. A hold position is suggested while signals resolve.`;
    }

    // ── Signal Breakdown ─────────────────────────────────────────────────────

    function renderSignals(signals) {
        _lastSignals = signals;  // cache for re-render on tab switch
        const labels    = Object.keys(signals).map(s => s.replace('_', ' ').toUpperCase());
        const strengths = Object.values(signals).map(s => s.strength || 0.5);
        const colors    = Object.values(signals).map(s => App.signalColor(s.signal));

        App.chart.create('signalsRadar', 'signals-radar', {
            type: 'radar',
            data: {
                labels,
                datasets: [{
                    label: 'Signal Strength', data: strengths,
                    backgroundColor: 'rgba(41,121,255,0.15)', borderColor: '#2979ff',
                    pointBackgroundColor: colors, pointRadius: 6, borderWidth: 2,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: true,
                scales: { r: { beginAtZero: true, max: 1, grid: { color: '#2a2e3f' }, ticks: { display: false } } },
                plugins: { legend: { display: false } },
            },
        });

        // Load weights chart asynchronously (separate from this sync function)
        loadWeightsChart(signals);

        // Signal rows — built with DOM methods (XSS-safe)
        const grid = App.$('signal-cards');
        grid.innerHTML = '';
        const frag = document.createDocumentFragment();

        for (const [name, sig] of Object.entries(signals)) {
            const direction = sig.signal || 'neutral';
            const strength  = sig.strength || 0.5;
            const pct = Math.round(strength * 100);
            const icon = direction === 'bullish' ? '\u25B2' : direction === 'bearish' ? '\u25BC' : '\u25C6';

            const row = document.createElement('div');
            row.className = 'signal-row';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'signal-row-name';
            nameSpan.textContent = name.replace(/_/g, ' ');

            const dirSpan = document.createElement('span');
            dirSpan.className = `signal-row-dir ${direction}`;
            dirSpan.textContent = `${icon} ${direction}`;

            const barWrap = document.createElement('div');
            barWrap.className = 'signal-row-bar-wrap';
            const bar = document.createElement('div');
            bar.className = `signal-row-bar ${direction}`;
            bar.style.width = `${pct}%`;
            barWrap.appendChild(bar);

            const valSpan = document.createElement('span');
            valSpan.className = 'signal-row-val';
            valSpan.textContent = strength.toFixed(2);

            row.append(nameSpan, dirSpan, barWrap, valSpan);
            frag.appendChild(row);
        }
        grid.appendChild(frag);
        App.show('signals-section');
    }

    // ── Reasons ──────────────────────────────────────────────────────────────

    function renderReasons(reasons) {
        const list = App.$('reasons-list');
        list.innerHTML = '';
        const frag = document.createDocumentFragment();

        reasons.forEach(r => {
            const li = document.createElement('li');
            const match = r.match(/^\[([^\]]+)\]\s*(.*)/);
            if (match) {
                const tag = document.createElement('span');
                tag.className = 'reason-tag';
                tag.textContent = match[1];
                li.appendChild(tag);
                li.appendChild(document.createTextNode(match[2]));
            } else {
                li.textContent = r;
            }
            frag.appendChild(li);
        });
        list.appendChild(frag);
        App.show('reasons-section');

        // Top reason card
        const topReason = reasons.find(r => !r.includes('[social') && !r.includes('[geopolitical') && !r.includes('No '));
        if (topReason) {
            const match = topReason.match(/^\[([^\]]+)\]\s*(.*)/);
            App.setText('top-reason-text', match ? match[2] : topReason);
            App.show('top-reason-card');
        }
    }

    // ── Charts (Price chart defined below with overlay support) ─────────────

    function renderRSIChart(data) {
        App.chart.create('rsi', 'rsi-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{ label: 'RSI', data: data.rsi, borderColor: '#7c4dff', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { min: 0, max: 100, grid: { color: '#1e2235' } },
                },
                plugins: { legend: { display: false } },
            },
            plugins: [{
                id: 'rsiZones',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    ctx.fillStyle = 'rgba(255,23,68,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(100), right - left, y.getPixelForValue(70) - y.getPixelForValue(100));
                    ctx.fillStyle = 'rgba(0,200,83,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(30), right - left, y.getPixelForValue(0) - y.getPixelForValue(30));
                    ctx.strokeStyle = '#444'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    [30, 70].forEach(val => {
                        const yPos = y.getPixelForValue(val);
                        ctx.beginPath(); ctx.moveTo(left, yPos); ctx.lineTo(right, yPos); ctx.stroke();
                    });
                    ctx.setLineDash([]);
                },
            }],
        });
    }

    function renderMACDChart(data) {
        const histogram = data.macd.map((m, i) => {
            const s = data.signal_line[i];
            return (m !== null && s !== null) ? +(m - s).toFixed(4) : null;
        });

        App.chart.create('macd', 'macd-chart', {
            type: 'bar',
            data: {
                labels: data.dates,
                datasets: [
                    { label: 'Histogram', data: histogram, backgroundColor: histogram.map(v => v >= 0 ? 'rgba(0,200,83,0.5)' : 'rgba(255,23,68,0.5)'), borderWidth: 0, barPercentage: 0.8, order: 2 },
                    { label: 'MACD', data: data.macd, type: 'line', borderColor: '#2979ff', borderWidth: 1.5, pointRadius: 0, tension: 0.3, order: 1 },
                    { label: 'Signal', data: data.signal_line, type: 'line', borderColor: '#ff6e40', borderWidth: 1.5, pointRadius: 0, tension: 0.3, order: 1 },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e2235' } },
                },
                plugins: { legend: { labels: { padding: 12 } } },
            },
        });
    }

    function renderVolumeChart(data) {
        App.chart.bar('volume', 'volume-chart', data.dates, [{
            label: 'Volume', data: data.volume,
            backgroundColor: data.close.map((c, i) => i > 0 && c >= data.close[i - 1] ? 'rgba(0,200,83,0.3)' : 'rgba(255,23,68,0.3)'),
            borderWidth: 0,
        }], {
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
                y: { grid: { color: '#1e2235' }, ticks: { callback: v => (v / 1e6).toFixed(0) + 'M' } },
            },
        });
    }

    // ── NEW: Stochastic Oscillator ──────────────────────────────────────────

    function renderStochChart(data) {
        App.chart.create('stoch', 'stoch-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [
                    { label: '%K', data: data.stoch_k, borderColor: '#2979ff', borderWidth: 2, pointRadius: 0, tension: 0.3 },
                    { label: '%D', data: data.stoch_d, borderColor: '#ff6e40', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4, 3] },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { min: 0, max: 100, grid: { color: '#1e2235' } },
                },
                plugins: { legend: { labels: { padding: 12 } } },
            },
            plugins: [{
                id: 'stochZones',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    ctx.fillStyle = 'rgba(255,23,68,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(100), right - left, y.getPixelForValue(80) - y.getPixelForValue(100));
                    ctx.fillStyle = 'rgba(0,200,83,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(20), right - left, y.getPixelForValue(0) - y.getPixelForValue(20));
                    ctx.strokeStyle = '#444'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    [20, 80].forEach(val => {
                        ctx.beginPath(); ctx.moveTo(left, y.getPixelForValue(val)); ctx.lineTo(right, y.getPixelForValue(val)); ctx.stroke();
                    });
                    ctx.setLineDash([]);
                },
            }],
        });
    }

    // ── NEW: Williams %R ─────────────────────────────────────────────────────

    function renderWilliamsChart(data) {
        App.chart.create('williams', 'williams-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{ label: 'Williams %R', data: data.williams_r, borderColor: '#7c4dff', borderWidth: 2, pointRadius: 0, tension: 0.3 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { min: -100, max: 0, grid: { color: '#1e2235' }, reverse: true },
                },
                plugins: { legend: { display: false } },
            },
            plugins: [{
                id: 'wrZones',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    ctx.fillStyle = 'rgba(255,23,68,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(-20), right - left, y.getPixelForValue(0) - y.getPixelForValue(-20));
                    ctx.fillStyle = 'rgba(0,200,83,0.07)';
                    ctx.fillRect(left, y.getPixelForValue(-100), right - left, y.getPixelForValue(-80) - y.getPixelForValue(-100));
                    ctx.strokeStyle = '#444'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    [-20, -80].forEach(val => {
                        ctx.beginPath(); ctx.moveTo(left, y.getPixelForValue(val)); ctx.lineTo(right, y.getPixelForValue(val)); ctx.stroke();
                    });
                    ctx.setLineDash([]);
                },
            }],
        });
    }

    // ── NEW: CCI ─────────────────────────────────────────────────────────────

    function renderCCIChart(data) {
        App.chart.create('cci', 'cci-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{ label: 'CCI', data: data.cci, borderColor: '#00e5ff', borderWidth: 2, pointRadius: 0, tension: 0.3 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e2235' } },
                },
                plugins: { legend: { display: false } },
            },
            plugins: [{
                id: 'cciZones',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    ctx.strokeStyle = '#444'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    [100, -100].forEach(val => {
                        ctx.beginPath(); ctx.moveTo(left, y.getPixelForValue(val)); ctx.lineTo(right, y.getPixelForValue(val)); ctx.stroke();
                    });
                    ctx.setLineDash([]);
                },
            }],
        });
    }

    // ── NEW: MACD Histogram (standalone) ─────────────────────────────────────

    function renderMACDHistChart(data) {
        const hist = data.macd_hist || [];
        App.chart.bar('macdHist', 'macd-hist-chart', data.dates, [{
            label: 'MACD Histogram', data: hist,
            backgroundColor: hist.map(v => v >= 0 ? 'rgba(0,200,83,0.5)' : 'rgba(255,23,68,0.5)'),
            borderWidth: 0, barPercentage: 0.8,
        }], {
            scales: {
                x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                y: { grid: { color: '#1e2235' } },
            },
        });
    }

    // ── NEW: ADX + DMI ───────────────────────────────────────────────────────

    function renderADXChart(data) {
        App.chart.create('adx', 'adx-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [
                    { label: 'ADX', data: data.adx, borderColor: '#ffc107', borderWidth: 2.5, pointRadius: 0, tension: 0.3 },
                    { label: '+DI', data: data.plus_di, borderColor: '#00c853', borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
                    { label: '-DI', data: data.minus_di, borderColor: '#ff1744', borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e2235' }, min: 0 },
                },
                plugins: { legend: { labels: { padding: 12 } } },
            },
            plugins: [{
                id: 'adxThreshold',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    ctx.strokeStyle = '#ffc10744'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
                    const yPos = y.getPixelForValue(25);
                    ctx.beginPath(); ctx.moveTo(left, yPos); ctx.lineTo(right, yPos); ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.fillStyle = '#ffc10722';
                    ctx.fillRect(left, y.getPixelForValue(100), right - left, yPos - y.getPixelForValue(100));
                },
            }],
        });
    }

    // ── NEW: OBV ─────────────────────────────────────────────────────────────

    function renderOBVChart(data) {
        const obv = data.obv || [];
        App.chart.create('obv', 'obv-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{
                    label: 'OBV', data: obv,
                    borderColor: '#00e5ff', backgroundColor: 'rgba(0,229,255,0.08)',
                    borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e2235' }, ticks: { callback: v => (v / 1e6).toFixed(0) + 'M' } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // ── NEW: ATR ─────────────────────────────────────────────────────────────

    function renderATRChart(data) {
        App.chart.create('atr', 'atr-chart', {
            type: 'line',
            data: {
                labels: data.dates,
                datasets: [{
                    label: 'ATR', data: data.atr,
                    borderColor: '#ff6e40', backgroundColor: 'rgba(255,110,64,0.08)',
                    borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
                    y: { grid: { color: '#1e2235' } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    // ── NEW: Overlay Toggles (EMA, VWAP, SAR, Fibonacci, Ichimoku) ──────────

    function setupOverlayToggles() {
        const container = App.$('overlay-toggles');
        if (!container) return;

        container.addEventListener('change', () => {
            if (_lastHist && _lastSymbol) renderPriceChart(_lastSymbol, _lastHist);
        });
    }

    function getActiveOverlays() {
        const checks = document.querySelectorAll('#overlay-toggles input[data-overlay]');
        const active = {};
        checks.forEach(c => { active[c.dataset.overlay] = c.checked; });
        return active;
    }

    // ── Price Chart with Overlay Support ─────────────────────────────────────

    function renderPriceChart(symbol, data) {
        const overlays = getActiveOverlays();
        const datasets = [
            { label: `${symbol} Close`, data: data.close, borderColor: '#2979ff', backgroundColor: 'rgba(41,121,255,0.08)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.3 },
            { label: 'SMA 20', data: data.sma_20, borderColor: '#ffc107', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 3] },
            { label: 'SMA 50', data: data.sma_50, borderColor: '#ff6e40', borderWidth: 1.5, pointRadius: 0, borderDash: [5, 3] },
            { label: 'BB Upper', data: data.bb_upper, borderColor: 'rgba(124,77,255,0.4)', borderWidth: 1, pointRadius: 0, borderDash: [2, 2] },
            { label: 'BB Lower', data: data.bb_lower, borderColor: 'rgba(124,77,255,0.4)', borderWidth: 1, pointRadius: 0, borderDash: [2, 2], fill: '-1', backgroundColor: 'rgba(124,77,255,0.05)' },
        ];

        // Conditional overlays
        if (overlays.ema) {
            datasets.push({ label: 'EMA 9', data: data.ema_9, borderColor: '#18ffff', borderWidth: 1.5, pointRadius: 0, borderDash: [3, 2] });
            datasets.push({ label: 'EMA 21', data: data.ema_21, borderColor: '#e040fb', borderWidth: 1.5, pointRadius: 0, borderDash: [3, 2] });
        }
        if (overlays.vwap && data.vwap) {
            datasets.push({ label: 'VWAP', data: data.vwap, borderColor: '#ffab40', borderWidth: 2, pointRadius: 0 });
        }
        if (overlays.sar && data.psar) {
            datasets.push({ label: 'SAR', data: data.psar, borderColor: '#76ff03', borderWidth: 0, pointRadius: 2, pointBackgroundColor: '#76ff03', showLine: false });
        }
        if (overlays.ichimoku) {
            datasets.push({ label: 'Tenkan', data: data.ichi_tenkan, borderColor: '#2979ff', borderWidth: 1, pointRadius: 0 });
            datasets.push({ label: 'Kijun', data: data.ichi_kijun, borderColor: '#ff1744', borderWidth: 1, pointRadius: 0 });
            datasets.push({ label: 'Span A', data: data.ichi_span_a, borderColor: 'rgba(0,200,83,0.5)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(0,200,83,0.06)' });
            datasets.push({ label: 'Span B', data: data.ichi_span_b, borderColor: 'rgba(255,23,68,0.5)', borderWidth: 1, pointRadius: 0 });
        }

        const plugins = [];
        if (overlays.fib && data.fibonacci) {
            plugins.push({
                id: 'fibLevels',
                beforeDraw(chart) {
                    const { ctx, chartArea: { left, right }, scales: { y } } = chart;
                    const fib = data.fibonacci;
                    const levels = [
                        { val: fib.level_236, label: '23.6%', color: '#69f0ae' },
                        { val: fib.level_382, label: '38.2%', color: '#ffc107' },
                        { val: fib.level_500, label: '50.0%', color: '#ff6e40' },
                        { val: fib.level_618, label: '61.8%', color: '#7c4dff' },
                        { val: fib.level_786, label: '78.6%', color: '#ff1744' },
                    ];
                    ctx.save();
                    levels.forEach(l => {
                        const yPos = y.getPixelForValue(l.val);
                        if (yPos < chart.chartArea.top || yPos > chart.chartArea.bottom) return;
                        ctx.strokeStyle = l.color + '60';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([6, 4]);
                        ctx.beginPath(); ctx.moveTo(left, yPos); ctx.lineTo(right, yPos); ctx.stroke();
                        ctx.fillStyle = l.color;
                        ctx.font = '10px sans-serif';
                        ctx.fillText(`${l.label} (${l.val.toFixed(2)})`, left + 4, yPos - 4);
                    });
                    ctx.restore();
                },
            });
        }

        App.chart.create('price', 'price-chart', {
            type: 'line',
            data: { labels: data.dates, datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    x: { grid: { display: false }, ticks: { maxTicksLimit: 12 } },
                    y: { grid: { color: '#1e2235' } },
                },
                plugins: { legend: { labels: { padding: 16 } } },
            },
            plugins,
        });
    }

    // ── NEW: Fundamentals ────────────────────────────────────────────────────

    async function loadWeightsChart(signals) {
        const weightColors = {
            technical: '#2979ff', news_sentiment: '#7c4dff', social_sentiment: '#00e5ff',
            geopolitical: '#ff6e40', market_momentum: '#ffc107', earnings: '#00c853',
            ml_model: '#e040fb',
        };
        const weightLabels = {
            technical: 'Technical', news_sentiment: 'News', social_sentiment: 'Social',
            geopolitical: 'Geopolitical', market_momentum: 'Momentum', earnings: 'Earnings',
            ml_model: 'ML Model',
        };

        const isMY = Object.keys(signals).some(k =>
            (signals[k]?.reasons || []).some(r => typeof r === 'string' && r.includes('.KL'))
        );

        const wData = await App.apiSilent('/api/weights');
        if (!wData) return;

        const mkt = isMY ? wData.MY : wData.US;
        if (!mkt || !mkt.weights) return;

        const w = mkt.weights;
        const labels = Object.keys(w).map(k => weightLabels[k] || k);
        const values = Object.values(w).map(v => Math.round(v * 100));
        const colors = Object.keys(w).map(k => weightColors[k] || '#888');

        // Cache for re-render on tab switch
        _lastWeightsData = { labels, values, colors };

        App.chart.doughnut('weightsDoughnut', 'weights-doughnut',
            labels, values, colors,
            { plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 }, color: '#9aa0b0', boxWidth: 12 } } } },
        );

        const badge = App.$('weight-source-badge');
        if (badge) {
            badge.textContent = mkt.source === 'ai_optimized' ? 'AI-Optimized' : 'Default Weights';
            badge.className = 'weight-source-badge ' + (mkt.source === 'ai_optimized' ? 'optimized' : 'default');
        }
    }

    async function loadFundamentals(symbol) {
        const grid = App.$('fundamentals-grid');
        if (!grid) return;
        grid.innerHTML = '<span class="hint">Loading fundamentals...</span>';

        const data = await App.apiSilent(`/api/fundamentals/${symbol}`);
        if (!data) { grid.innerHTML = '<span class="hint">Fundamentals not available</span>'; return; }

        const metrics = [
            { key: 'pe_ratio', label: 'P/E Ratio', fmt: v => v?.toFixed(1) },
            { key: 'forward_pe', label: 'Forward P/E', fmt: v => v?.toFixed(1) },
            { key: 'pb_ratio', label: 'P/B Ratio', fmt: v => v?.toFixed(2) },
            { key: 'eps', label: 'EPS', fmt: v => `$${v?.toFixed(2)}` },
            { key: 'eps_growth', label: 'EPS Growth', fmt: v => `${(v * 100).toFixed(1)}%`, color: true },
            { key: 'roe', label: 'ROE', fmt: v => `${(v * 100).toFixed(1)}%`, color: true },
            { key: 'profit_margin', label: 'Profit Margin', fmt: v => `${(v * 100).toFixed(1)}%`, color: true },
            { key: 'debt_to_equity', label: 'Debt/Equity', fmt: v => v?.toFixed(1) },
            { key: 'free_cash_flow', label: 'Free Cash Flow', fmt: v => {
                if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
                if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
                return `$${v?.toFixed(0)}`;
            }, color: true },
            { key: 'dividend_yield', label: 'Div Yield', fmt: v => `${(v * 100).toFixed(2)}%` },
            { key: 'beta', label: 'Beta', fmt: v => v?.toFixed(2) },
            { key: 'market_cap', label: 'Market Cap', fmt: v => {
                if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
                if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
                return `$${(v / 1e6).toFixed(0)}M`;
            }},
            { key: '52w_high', label: '52W High', fmt: v => v?.toFixed(2) },
            { key: '52w_low', label: '52W Low', fmt: v => v?.toFixed(2) },
        ];

        grid.innerHTML = '';
        const frag = document.createDocumentFragment();
        metrics.forEach(m => {
            const val = data[m.key];
            if (val == null) return;
            const div = document.createElement('div');
            div.className = 'fund-metric';
            const label = document.createElement('span');
            label.className = 'fund-metric-label';
            label.textContent = m.label;
            const value = document.createElement('span');
            value.className = 'fund-metric-value';
            try { value.textContent = m.fmt(val); } catch { value.textContent = val; }
            if (m.color && val > 0) value.classList.add('positive');
            if (m.color && val < 0) value.classList.add('negative');
            div.append(label, value);
            frag.appendChild(div);
        });
        grid.appendChild(frag);
    }

    // ── Earnings Report ────────────────────────────────────────────────────

    async function loadEarnings(symbol) {
        const section = App.$('earnings-section');
        const signalBar = App.$('earnings-signal-bar');
        const nextEl = App.$('earnings-next');
        const tbody = App.$('earnings-table-body');
        if (!section || !tbody) return;

        // Hide initially
        section.style.display = 'none';
        signalBar.innerHTML = '';
        nextEl.textContent = '';
        tbody.innerHTML = '';

        const data = await App.apiSilent(`/api/signal/earnings/${symbol}`);
        if (!data || !data.signal || !data.signal.has_data) return;

        const sig = data.signal;
        section.style.display = '';

        // Signal badge
        const badgeClass = sig.signal === 'bullish' ? 'beat' : sig.signal === 'bearish' ? 'miss' : 'neutral';
        const badgeLabel = sig.signal === 'bullish' ? 'BEAT' : sig.signal === 'bearish' ? 'MISS' : 'MET';

        const badge = document.createElement('span');
        badge.className = `earnings-badge ${badgeClass}`;
        badge.textContent = `Latest: ${badgeLabel}`;
        signalBar.appendChild(badge);

        if (sig.latest_surprise_pct != null) {
            const stat = document.createElement('span');
            stat.className = 'earnings-stat';
            stat.innerHTML = `Surprise: <strong>${sig.latest_surprise_pct > 0 ? '+' : ''}${sig.latest_surprise_pct.toFixed(1)}%</strong>`;
            signalBar.appendChild(stat);
        }

        if (sig.beat_rate != null) {
            const stat = document.createElement('span');
            stat.className = 'earnings-stat';
            stat.innerHTML = `Beat rate: <strong>${(sig.beat_rate * 100).toFixed(0)}%</strong> (${sig.quarters_analyzed}Q)`;
            signalBar.appendChild(stat);
        }

        // Next earnings date
        if (sig.days_to_next_earnings != null) {
            nextEl.textContent = sig.days_to_next_earnings <= 0
                ? 'Earnings reporting today'
                : `Next earnings in ${sig.days_to_next_earnings} day${sig.days_to_next_earnings !== 1 ? 's' : ''}`;
        }

        // Fetch full history for the table
        const histData = await App.apiSilent(`/api/earnings/history/${symbol}`);
        if (!histData || !histData.earnings || !histData.earnings.length) return;

        const frag = document.createDocumentFragment();
        histData.earnings.forEach(e => {
            const tr = document.createElement('tr');

            const tdPeriod = document.createElement('td');
            tdPeriod.textContent = e.period || '—';
            tdPeriod.style.fontWeight = '600';

            const tdDate = document.createElement('td');
            tdDate.textContent = e.date || '—';
            tdDate.style.color = 'var(--text-secondary)';

            const tdEst = document.createElement('td');
            tdEst.textContent = e.eps_estimate != null ? e.eps_estimate.toFixed(2) : '—';

            const tdActual = document.createElement('td');
            tdActual.textContent = e.eps_actual != null ? e.eps_actual.toFixed(2) : '—';
            if (e.eps_actual != null && e.eps_estimate != null) {
                tdActual.style.fontWeight = '600';
                tdActual.style.color = e.eps_actual >= e.eps_estimate ? '#00c853' : '#ff1744';
            }

            const tdSurprise = document.createElement('td');
            if (e.surprise_pct != null) {
                const sign = e.surprise_pct > 0 ? '+' : '';
                tdSurprise.textContent = `${sign}${e.surprise_pct.toFixed(1)}%`;
                tdSurprise.className = e.surprise_pct > 0 ? 'surprise-beat' : e.surprise_pct < 0 ? 'surprise-miss' : 'surprise-met';
            } else {
                tdSurprise.textContent = '—';
            }

            tr.append(tdPeriod, tdDate, tdEst, tdActual, tdSurprise);
            frag.appendChild(tr);
        });
        tbody.appendChild(frag);
    }

    // ── NEW: Market Movers (Influential Figures) ───────────────────────────

    async function loadMarketMovers(symbol) {
        const card = App.$('market-movers-card');
        const figuresEl = App.$('mm-figures');
        const emptyEl = App.$('mm-empty');
        const signalEl = App.$('mm-signal');

        if (!card) return;
        App.hide('market-movers-card');

        const data = await App.apiSilent(`/api/market-movers?symbol=${encodeURIComponent(symbol)}`);
        if (!data || !data.figures || !data.figures.length) {
            figuresEl.innerHTML = '';
            App.show('mm-empty');
            App.show('market-movers-card');
            return;
        }

        App.hide('mm-empty');

        // Signal badge
        signalEl.textContent = `${data.signal} \u00B7 ${data.total_mentions} mentions`;
        signalEl.className = `mm-signal-badge ${data.signal}`;

        // Render figures
        figuresEl.innerHTML = '';
        const frag = document.createDocumentFragment();

        data.figures.forEach(fig => {
            const el = document.createElement('div');
            el.className = 'mm-figure';

            const top = document.createElement('div');
            top.className = 'mm-figure-top';

            const name = document.createElement('span');
            name.className = 'mm-figure-name';
            name.textContent = fig.name;

            const badge = document.createElement('span');
            badge.className = `mm-figure-badge ${fig.signal}`;
            badge.textContent = fig.signal;

            top.append(name, badge);

            const meta = document.createElement('div');
            meta.className = 'mm-figure-meta';
            const countSpan = document.createElement('span');
            countSpan.className = 'mm-mention-count';
            countSpan.textContent = `${fig.mention_count} mention${fig.mention_count > 1 ? 's' : ''}`;
            const sentSpan = document.createElement('span');
            sentSpan.textContent = `Sentiment: ${fig.avg_sentiment > 0 ? '+' : ''}${fig.avg_sentiment.toFixed(3)}`;
            meta.append(countSpan, sentSpan);

            el.append(top, meta);

            // Latest headline
            if (fig.latest_headline) {
                const headline = document.createElement('div');
                headline.className = 'mm-headline';
                if (fig.latest_url) {
                    const a = document.createElement('a');
                    a.href = fig.latest_url;
                    a.target = '_blank';
                    a.rel = 'noopener';
                    a.textContent = fig.latest_headline;
                    headline.appendChild(a);
                } else {
                    headline.textContent = fig.latest_headline;
                }
                el.appendChild(headline);

                if (fig.latest_source) {
                    const src = document.createElement('div');
                    src.className = 'mm-source';
                    src.textContent = `${fig.latest_source} \u00B7 ${App.timeAgo(fig.latest_datetime)}`;
                    el.appendChild(src);
                }
            }

            frag.appendChild(el);
        });

        figuresEl.appendChild(frag);
        App.show('market-movers-card');
    }

    // Setup overlay toggles on load
    setupOverlayToggles();

    // ── Re-render functions (called by tab switch in main.js) ──────────────

    function _rerenderRadar() {
        if (_lastSignals) {
            const labels    = Object.keys(_lastSignals).map(s => s.replace('_', ' ').toUpperCase());
            const strengths = Object.values(_lastSignals).map(s => s.strength || 0.5);
            const colors    = Object.values(_lastSignals).map(s => App.signalColor(s.signal));

            App.chart.create('signalsRadar', 'signals-radar', {
                type: 'radar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Signal Strength', data: strengths,
                        backgroundColor: 'rgba(41,121,255,0.15)', borderColor: '#2979ff',
                        pointBackgroundColor: colors, pointRadius: 6, borderWidth: 2,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: true,
                    scales: { r: { beginAtZero: true, max: 1, grid: { color: '#2a2e3f' }, ticks: { display: false } } },
                    plugins: { legend: { display: false } },
                },
            });
        }
    }

    function _rerenderWeights() {
        if (_lastWeightsData) {
            const { labels, values, colors } = _lastWeightsData;
            App.chart.doughnut('weightsDoughnut', 'weights-doughnut',
                labels, values, colors,
                { plugins: { legend: { position: 'bottom', labels: { padding: 10, font: { size: 11 }, color: '#9aa0b0', boxWidth: 12 } } } },
            );
        }
    }

    // ── Public API ───────────────────────────────────────────────────────────
    App.tabs.analysis = { switchMarket, quickAnalyze, analyze, _rerenderRadar, _rerenderWeights };
})();
