/* ===== tab-sectors.js — Sector Heatmap tab ===== */

(function () {
    const SECTOR_COUNT = 11;
    let _progressInterval = null;

    function showProgress() {
        const loadingEl = App.$('sector-loading');
        if (!loadingEl) return;
        // Replace spinner with progress bar
        loadingEl.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.style.cssText = 'width:100%;max-width:400px;margin:0 auto;';

        const text = document.createElement('div');
        text.className = 'sector-progress-text';
        text.id = 'sector-progress-text';
        text.textContent = 'Analysing sectors\u2026 0/' + SECTOR_COUNT;
        text.style.textAlign = 'center';
        text.style.marginBottom = '8px';

        const bar = document.createElement('div');
        bar.className = 'sector-progress-bar';
        const fill = document.createElement('div');
        fill.className = 'sector-progress-fill';
        fill.id = 'sector-progress-fill';
        fill.style.width = '0%';
        bar.appendChild(fill);

        wrap.appendChild(text);
        wrap.appendChild(bar);
        loadingEl.appendChild(wrap);

        // Simulate progress (each sector ~2-4s)
        let progress = 0;
        _progressInterval = setInterval(() => {
            progress = Math.min(progress + 1, SECTOR_COUNT - 1); // cap at 10/11, last one filled on completion
            const pct = Math.round((progress / SECTOR_COUNT) * 100);
            fill.style.width = pct + '%';
            text.textContent = `Analysing sectors\u2026 ${progress}/${SECTOR_COUNT}`;
        }, 3000);
    }

    function hideProgress() {
        if (_progressInterval) { clearInterval(_progressInterval); _progressInterval = null; }
        const fill = App.$('sector-progress-fill');
        const text = App.$('sector-progress-text');
        if (fill) fill.style.width = '100%';
        if (text) text.textContent = `Done \u2014 ${SECTOR_COUNT}/${SECTOR_COUNT} sectors`;
    }

    async function load() {
        // Check cache first
        const cacheKey = `sectors_${App.state.market}`;
        const cached = App.cacheGet(cacheKey);
        if (cached) {
            render(cached.sectors);
            App.show('sector-heatmap');
            return;
        }

        App.show('sector-loading');
        App.hide('sector-heatmap');
        showProgress();

        try {
            const data = await App.api(`/api/sectors?market=${App.state.market}`);
            hideProgress();
            App.hide('sector-loading');
            App.cacheSet(cacheKey, data);
            render(data.sectors);
            App.show('sector-heatmap');
        } catch (err) {
            hideProgress();
            App.hide('sector-loading');
            App.toast(err.message, 'error');
        }
    }

    function render(sectors) {
        // Bar chart
        const labels = sectors.map(s => s.name);
        const scores = sectors.map(s => s.score);
        const colors = scores.map(s => s > 0.15 ? '#00c853' : s < -0.15 ? '#ff1744' : '#ffc107');

        App.chart.create('sectorBar', 'sector-bar-chart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{ label: 'Sector Score', data: scores, backgroundColor: colors, borderRadius: 6, borderWidth: 0 }],
            },
            options: {
                indexAxis: 'y', responsive: true,
                scales: {
                    x: { grid: { color: '#1e2235' }, min: -1, max: 1 },
                    y: { grid: { display: false } },
                },
                plugins: { legend: { display: false } },
            },
        });

        // Radar — top 5 sectors
        const top5 = sectors.slice(0, 5);
        const radarLabels = ['Technical', 'News', 'Social', 'Geopolitical', 'Momentum'];
        const radarColors = ['#2979ff', '#00e5ff', '#7c4dff', '#ffc107', '#ff6e40'];

        App.chart.create('sectorRadar', 'sector-radar-chart', {
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
                    borderColor: radarColors[i], backgroundColor: radarColors[i] + '15',
                    borderWidth: 2, pointRadius: 3,
                })),
            },
            options: {
                scales: { r: { beginAtZero: true, max: 1, grid: { color: '#2a2e3f' }, ticks: { display: false } } },
                plugins: { legend: { position: 'bottom', labels: { padding: 16 } } },
            },
        });

        // Ranked list — XSS-safe DOM construction
        const grid = App.$('sector-grid');
        grid.innerHTML = '';
        const frag = document.createDocumentFragment();

        sectors.forEach((s, i) => {
            const acColor = App.actionColor(s.action);
            const scoreDisplay = s.score >= 0 ? `+${s.score.toFixed(3)}` : s.score.toFixed(3);
            const scoreColor = s.score > 0 ? 'var(--accent-green)' : s.score < 0 ? 'var(--accent-red)' : 'var(--accent-yellow)';
            const confPct = Math.round((s.confidence || 0) * 100);
            const isTop = i < 3;
            const isBot = i >= sectors.length - 3;

            const row = document.createElement('div');
            row.className = `sector-rank-row ${isTop ? 'rank-top' : isBot ? 'rank-bot' : ''}`;
            row.style.borderLeftColor = acColor;

            row.innerHTML = `
                <div class="sector-rank-num">${i + 1}</div>
                <div class="sector-rank-body">
                    <div class="sector-rank-top-row">
                        <span class="sector-rank-name">${App.esc(s.name)}</span>
                        <span class="sector-rank-score" style="color:${scoreColor}">${scoreDisplay}</span>
                    </div>
                    <div class="sector-rank-bar-row">
                        <div class="sector-rank-bar-wrap">
                            <div class="sector-rank-bar" style="width:${confPct}%;background:${acColor}80"></div>
                        </div>
                        <span class="sector-rank-conf">${confPct}%</span>
                    </div>
                    <div class="sector-rank-meta">
                        <span class="sector-rank-badge" style="background:${acColor}22;color:${acColor};border:1px solid ${acColor}44">${App.esc(s.action)}</span>
                        <span class="sector-rank-etf">ETF: ${App.esc(s.etf)}</span>
                        <span class="sector-rank-symbols">${(s.symbols || []).slice(0, 3).map(App.esc).join(' \u00B7 ')}</span>
                    </div>
                </div>`;
            frag.appendChild(row);
        });
        grid.appendChild(frag);
    }

    App.tabs.sectors = { load };
})();
