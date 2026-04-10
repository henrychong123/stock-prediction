/* ===== tab-news.js — News Intelligence Hub tab ===== */

(function () {

    function setRange(hours, btn) {
        App.state.news.hoursBack = hours;
        document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        // Invalidate cache for new range
        delete App.state.cache[`news_${hours || 'all'}`];
        delete App.state.cache._ts[`news_${hours || 'all'}`];
        loadIndustryAnalysis();
    }

    function updateStatusBar(latestFetched) {
        const el  = App.$('news-last-updated');
        const dot = App.$('news-status-dot');
        if (!el) return;
        if (!latestFetched) {
            el.textContent = 'No data yet';
            if (dot) dot.className = 'news-status-dot stale';
            return;
        }
        const then = new Date(latestFetched.replace(' ', 'T') + 'Z');
        const diffMin = Math.round((Date.now() - then) / 60000);
        el.textContent = `Updated ${App.timeAgo(latestFetched)}`;
        if (dot) dot.className = 'news-status-dot ' + (diffMin < 60 ? 'fresh' : diffMin < 180 ? 'ok' : 'stale');
    }

    async function pollStatus() {
        const d = await App.apiSilent('/api/news/status');
        if (d) updateStatusBar(d.latest_fetched);
    }

    function startPoller() {
        pollStatus();
        if (App.state.news.statusTimer) clearInterval(App.state.news.statusTimer);
        App.state.news.statusTimer = setInterval(pollStatus, 120000);
    }

    async function fetchAll() {
        const btn = App.$('fetch-all-news-btn');
        if (btn) { btn.disabled = true; btn.textContent = '\u21BB Fetching\u2026'; }
        App.show('newshub-loading');
        App.hide('newshub-stats');
        App.hide('industry-grid');

        await App.apiSilent('/api/news/fetch-all');

        if (btn) { btn.disabled = false; btn.textContent = '\u21BB Fetch'; }
        await loadIndustryAnalysis();
        pollStatus();
    }

    async function loadIndustryAnalysis() {
        // Check cache
        const cacheKey = `news_${App.state.news.hoursBack || 'all'}`;
        const cached = App.cacheGet(cacheKey);
        if (cached) {
            updateStatusBar(cached.latest_fetched);
            renderStats(cached.total_articles, cached.industries.length, cached.stats || {});
            renderIndustryCards(cached.industries);
            return;
        }

        App.show('newshub-loading');
        App.hide('newshub-stats');
        App.hide('industry-grid');
        // Show skeleton placeholders
        App.showSkeleton('industry-cards', 6, 'card');
        App.show('industry-grid');

        try {
            const params = new URLSearchParams({ limit: 500 });
            if (App.state.news.hoursBack) params.set('hours_back', App.state.news.hoursBack);

            const data = await App.api(`/api/news/industry-analysis?${params}`);
            App.hide('newshub-loading');
            App.cacheSet(cacheKey, data);

            updateStatusBar(data.latest_fetched);
            renderStats(data.total_articles, data.industries.length, data.stats || {});
            renderIndustryCards(data.industries);
        } catch (err) {
            App.hide('newshub-loading');
            App.toast(err.message, 'error');
        }
    }

    function renderStats(totalArticles, industryCount, stats) {
        App.setText('stat-total', totalArticles || 0);
        App.setText('stat-industries', industryCount || 0);

        const sentiments = stats.by_sentiment || {};
        const pos   = sentiments.positive || 0;
        const total = pos + (sentiments.negative || 0) + (sentiments.neutral || 0);
        if (total > 0) {
            const pct = ((pos / total) * 100).toFixed(0);
            const el = App.$('stat-sentiment');
            el.innerHTML = '';
            const sp = document.createElement('span');
            sp.style.color = '#00c853';
            sp.textContent = `${pct}%`;
            el.appendChild(sp);
        }

        // Platform pie
        const platforms = stats.by_platform || {};
        const platLabels = Object.keys(platforms);
        const platColors = {
            finnhub: '#2979ff', 'finnhub-figures': '#7c4dff',
            gdelt: '#ff6e40', reddit: '#ff4500',
            'google-news-my': '#00c853', 'theedge-my': '#00e5ff', 'newsapi-my': '#ffc107',
        };
        App.chart.doughnut('platformPie', 'platform-pie-chart',
            platLabels, Object.values(platforms),
            platLabels.map(l => platColors[l] || '#9aa0b0'),
        );

        // Sentiment pie
        App.chart.doughnut('sentimentPie', 'sentiment-pie-chart',
            ['Positive', 'Negative', 'Neutral'],
            [sentiments.positive || 0, sentiments.negative || 0, sentiments.neutral || 0],
            ['#00c853', '#ff1744', '#ffc107'],
        );

        App.show('newshub-stats');
    }

    function renderIndustryCards(industries) {
        const grid = App.$('industry-cards');
        grid.innerHTML = '';
        const frag = document.createDocumentFragment();

        industries.forEach((ind, i) => {
            const verdictClass = ind.verdict.toLowerCase();
            const verdictIcon = ind.verdict === 'BULLISH' ? '\u25B2' : ind.verdict === 'BEARISH' ? '\u25BC' : '\u25C6';
            const confPct = Math.round(ind.confidence * 100);
            const scoreSign = ind.avg_score >= 0 ? '+' : '';

            // Articles HTML (headlines from API — escape headline text)
            const articlesHtml = ind.top_headlines.map(a => {
                const sc = a.score >= 0 ? `+${a.score.toFixed(3)}` : a.score.toFixed(3);
                const urlAttr = a.url ? ` href="${App.esc(a.url)}" target="_blank"` : '';
                const platClass = (a.platform || 'unknown').replace(/[^a-z0-9-]/g, '-');
                const ts = a.fetched_at ? App.timeAgo(a.fetched_at) : '';
                return `
                    <div class="ind-article">
                        <a class="ind-article-headline"${urlAttr}>${App.esc(a.headline || '\u2014')}</a>
                        <div class="ind-article-meta">
                            <span class="platform-tag ${platClass}">${App.esc(a.platform || '')}</span>
                            <span class="sentiment-badge ${a.sentiment}">${App.esc(a.sentiment)} (${sc})</span>
                            <span>${App.esc(a.source || '')}</span>
                            ${ts ? `<span class="ind-article-time">\u00B7 ${ts}</span>` : ''}
                        </div>
                    </div>`;
            }).join('');

            // Related stock chips — use data attributes for event delegation
            const stocksHtml = (ind.related_stocks || []).map(s => `
                <button class="stock-chip" data-stock-symbol="${App.esc(s.symbol)}" title="${App.esc(s.symbol)}">
                    ${App.esc(s.name)}
                </button>`).join('');

            const card = document.createElement('div');
            card.className = 'industry-card';
            card.id = `ind-card-${i}`;
            card.innerHTML = `
                <div class="industry-card-header" data-toggle-industry="${i}">
                    <div class="ind-title-row">
                        <span class="ind-icon">${ind.icon}</span>
                        <span class="ind-name">${App.esc(ind.industry)}</span>
                        <span class="verdict-badge ${verdictClass}">${verdictIcon} ${App.esc(ind.verdict)}</span>
                    </div>
                    <div class="ind-meta-row">
                        <span class="ind-meta-item">${ind.article_count} articles</span>
                        <span class="ind-meta-item">Avg score: <strong>${scoreSign}${ind.avg_score.toFixed(3)}</strong></span>
                        <span class="ind-meta-item">
                            <span style="color:#00c853">\u25B2${ind.positive_count}</span>
                            <span style="color:#ff1744">\u25BC${ind.negative_count}</span>
                            <span style="color:#9aa0b0">\u25C6${ind.neutral_count}</span>
                        </span>
                        <span class="ind-expand-hint">\u25BE ${ind.top_headlines.length} headlines</span>
                    </div>
                    <div class="ind-confidence-bar">
                        <div class="ind-confidence-fill ${verdictClass}" style="width:${confPct}%"></div>
                    </div>
                    <div class="ind-confidence-label">${confPct}% confidence</div>
                    <div class="ind-reasoning">${App.esc(ind.reasoning)}</div>
                </div>
                ${stocksHtml ? `<div class="ind-stocks">${stocksHtml}</div>` : ''}
                <div class="ind-articles hidden" id="ind-articles-${i}">
                    ${articlesHtml}
                </div>`;
            frag.appendChild(card);
        });
        grid.appendChild(frag);

        // Event delegation for industry toggle + stock chips
        grid.addEventListener('click', e => {
            // Toggle industry articles
            const header = e.target.closest('[data-toggle-industry]');
            if (header) {
                const idx = header.dataset.toggleIndustry;
                const articles = App.$(`ind-articles-${idx}`);
                const hint = document.querySelector(`#ind-card-${idx} .ind-expand-hint`);
                if (articles.classList.contains('hidden')) {
                    articles.classList.remove('hidden');
                    if (hint) hint.textContent = '\u25B4 collapse';
                } else {
                    articles.classList.add('hidden');
                    const count = articles.querySelectorAll('.ind-article').length;
                    if (hint) hint.textContent = `\u25BE ${count} headlines`;
                }
                return;
            }

            // Stock chip click → open in Bursa modal
            const chip = e.target.closest('[data-stock-symbol]');
            if (chip && App.tabs.bursa) {
                App.tabs.bursa.openStockModal(chip.dataset.stockSymbol);
            }
        });

        App.show('industry-grid');
    }

    App.tabs.news = { setRange, fetchAll, loadIndustryAnalysis, startPoller };
})();
