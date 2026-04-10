/* ===== tab-bursa.js — Bursa Market + Order Book + Stock Modal ===== */

(function () {
    const REFRESH_MS = 30000;

    // ── Market Hours ─────────────────────────────────────────────────────────

    function isBursaOpen() {
        const now = new Date();
        const myt = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kuala_Lumpur' }));
        const day = myt.getDay();
        if (day === 0 || day === 6) return false;
        const t = myt.getHours() * 60 + myt.getMinutes();
        return (t >= 540 && t <= 750) || (t >= 870 && t <= 1020);
    }

    // ── KLCI Bar Update ────────────────────────────────────────────────────

    function updateKlciBar(klciData) {
        const klci = (klciData.quotes || []).find(q => q.symbol === '^KLSE');
        if (klci && !klci.error) {
            App.state.bursa.klciData = klci;
            App.setText('klci-price', klci.price.toFixed(2));
            const sign = klci.change_pct >= 0 ? '+' : '';
            const changeEl = App.$('klci-change');
            changeEl.innerHTML = '';
            const sp = document.createElement('span');
            sp.className = klci.change_pct >= 0 ? 'up' : 'down';
            sp.textContent = `${sign}${klci.change_abs.toFixed(2)} (${sign}${klci.change_pct.toFixed(2)}%)`;
            changeEl.appendChild(sp);
        }

        const open = isBursaOpen();
        const statusEl = App.$('bursa-market-status');
        statusEl.textContent = open ? 'OPEN' : 'CLOSED';
        statusEl.className = `market-status-badge ${open ? 'open' : 'closed'}`;
        const closedMsg = App.$('bursa-closed-msg');
        if (closedMsg) closedMsg.classList.toggle('hidden', open);

        const ts = new Date(klciData.timestamp);
        App.setText('bursa-last-updated',
            `Updated ${ts.toLocaleTimeString('en-MY', { hour: '2-digit', minute: '2-digit' })}`);
    }

    // ── Load Market Data ─────────────────────────────────────────────────────

    function _initBursaSteps() {
        const stepsEl = App.$('bursa-steps');
        if (!stepsEl) return;
        const steps = [
            { id: 'b-klci', label: 'KLCI Index' },
            { id: 'b-industries', label: 'Industries' },
            { id: 'b-render', label: 'Rendering' },
            { id: 'b-predictions', label: 'Predictions' },
        ];
        stepsEl.innerHTML = '';
        steps.forEach(s => {
            const el = document.createElement('span');
            el.className = 'analysis-step';
            el.id = `step-${s.id}`;
            el.innerHTML = `<span class="analysis-step-icon">\u25CB</span> ${s.label}`;
            stepsEl.appendChild(el);
        });
    }

    function _setBursaStep(id, state) {
        const el = App.$(`step-${id}`);
        if (!el) return;
        el.className = `analysis-step ${state}`;
        const icon = state === 'done' ? '\u2713' : state === 'running' ? '\u25CF' : '\u25CB';
        el.querySelector('.analysis-step-icon').textContent = icon;
    }

    function _setBursaStatus(msg) {
        const el = App.$('bursa-status-text');
        if (el) el.textContent = msg;
    }

    async function loadMarket(forceRefresh = false) {
        // Use cache if fresh and not forced
        if (!forceRefresh) {
            const cached = App.cacheGet('bursa_market');
            if (cached) {
                updateKlciBar(cached.klciData);
                renderIndustries(cached.industries);
                App.show('bursa-industry-grid');
                injectPredictionBadges();
                return;
            }
        }

        App.show('bursa-loading');
        App.hide('bursa-industry-grid');
        _initBursaSteps();

        // Show skeleton placeholders
        App.showSkeleton('bursa-industry-cards', 4, 'card');
        App.show('bursa-industry-grid');

        try {
            // Step 1 & 2: Fetch KLCI + industries in parallel
            _setBursaStep('b-klci', 'running');
            _setBursaStep('b-industries', 'running');
            _setBursaStatus('Fetching KLCI index & industry quotes\u2026');

            const klciPromise = App.api('/api/bursa/watchlist');
            const indPromise = App.api('/api/bursa/industries');

            const klciData = await klciPromise;
            _setBursaStep('b-klci', 'done');
            updateKlciBar(klciData);

            const indData = await indPromise;
            _setBursaStep('b-industries', 'done');

            // Step 3: Render
            _setBursaStep('b-render', 'running');
            _setBursaStatus('Rendering industry cards\u2026');

            App.cacheSet('bursa_market', { klciData, industries: indData.industries || [] });
            renderIndustries(indData.industries || []);
            App.show('bursa-industry-grid');
            _setBursaStep('b-render', 'done');

            // Step 4: Prediction badges
            _setBursaStep('b-predictions', 'running');
            _setBursaStatus('Loading prediction badges\u2026');
            await injectPredictionBadges();
            _setBursaStep('b-predictions', 'done');

            _setBursaStatus('Done');
            App.hide('bursa-loading');

            if (isBursaOpen() && App.state.bursa.autoRefresh) {
                if (App.state.bursa.refreshTimer) clearTimeout(App.state.bursa.refreshTimer);
                App.state.bursa.refreshTimer = setTimeout(() => loadMarket(true), REFRESH_MS);
            }
        } catch (err) {
            App.hide('bursa-loading');
            App.toast(err.message, 'error');
        }
    }

    function renderIndustries(industries) {
        const container = App.$('bursa-industry-cards');
        container.innerHTML = '';
        const frag = document.createDocumentFragment();

        industries.forEach(ind => {
            const validStocks = ind.stocks.filter(s => s.price != null);
            const gainers = validStocks.filter(s => s.change_pct > 0).length;
            const losers  = validStocks.filter(s => s.change_pct < 0).length;
            const avgChg  = validStocks.length
                ? validStocks.reduce((a, s) => a + s.change_pct, 0) / validStocks.length : 0;
            const sectorDir = avgChg > 0.1 ? 'up' : avgChg < -0.1 ? 'down' : 'flat';

            const stockRows = ind.stocks.map(s => {
                if (s.price == null) return `
                    <div class="bi-stock-row bi-stock-na">
                        <div class="bi-stock-left">
                            <span class="bi-stock-name">${App.esc(s.name)}</span>
                            <span class="bi-stock-code">${App.esc(s.symbol.replace('.KL',''))}</span>
                        </div>
                        <span class="hint" style="font-size:0.7rem">\u2014</span>
                    </div>`;
                const sign = s.change_pct >= 0 ? '+' : '';
                const dir  = s.change_pct >= 0 ? 'up' : 'down';
                return `
                    <div class="bi-stock-row" data-sym="${App.esc(s.symbol)}" data-name="${App.esc(s.name)}">
                        <div class="bi-stock-left">
                            <span class="bi-stock-name">${App.esc(s.name)}</span>
                            <span class="bi-stock-code">${App.esc(s.symbol.replace('.KL',''))}</span>
                        </div>
                        <div class="bi-stock-right">
                            <span class="bi-stock-price">MYR ${s.price.toFixed(3)}</span>
                            <span class="bi-stock-chg ${dir}">${sign}${s.change_pct.toFixed(2)}%</span>
                        </div>
                    </div>`;
            }).join('');

            const card = document.createElement('div');
            card.className = 'card bi-card';
            card.innerHTML = `
                <div class="bi-header">
                    <div class="bi-header-left">
                        <span class="bi-icon">${ind.icon}</span>
                        <span class="bi-title">${App.esc(ind.industry)}</span>
                    </div>
                    <div class="bi-header-right">
                        <span class="bi-avg ${sectorDir}">${avgChg >= 0 ? '+' : ''}${avgChg.toFixed(2)}% avg</span>
                        <span class="bi-gl"><span class="up">\u25B2${gainers}</span> <span class="down">\u25BC${losers}</span></span>
                    </div>
                </div>
                <div class="bi-stock-list">${stockRows}</div>`;
            frag.appendChild(card);
        });
        container.appendChild(frag);

        // Event delegation for stock row clicks
        container.addEventListener('click', e => {
            const row = e.target.closest('.bi-stock-row[data-sym]');
            if (row) openDetail(row.dataset.sym, row.dataset.name);
        });
    }

    // ── Prediction Badges on Stock Rows ─────────────────────────────────────

    async function injectPredictionBadges() {
        const data = await App.apiSilent('/api/predictions/latest');
        if (!data || !data.predictions) return;

        const preds = data.predictions;
        document.querySelectorAll('.bi-stock-row[data-sym]').forEach(row => {
            const sym = row.dataset.sym;
            const pred = preds[sym];
            if (!pred) return;

            // Remove existing badge if any
            row.querySelector('.bi-pred-badge')?.remove();

            const badge = document.createElement('span');
            badge.className = `bi-pred-badge action-${App.actionClass(pred.action)}`;
            badge.textContent = pred.action;
            badge.title = `${pred.action} (${(pred.confidence * 100).toFixed(0)}% confidence)`;

            const rightDiv = row.querySelector('.bi-stock-right');
            if (rightDiv) rightDiv.appendChild(badge);
        });
    }

    // ── Stock Detail Panel ───────────────────────────────────────────────────

    function openDetail(symbol, name) {
        const bs = App.state.bursa;
        bs.detailSymbol = symbol;
        bs.detailPeriod = '1d';

        App.setText('bursa-detail-symbol', symbol.replace('.KL', ''));
        App.setText('bursa-detail-name', name);
        App.setText('bursa-detail-price', '\u2014');
        App.setText('bursa-detail-change', '');
        App.$('bursa-detail-fullpage').href = `/stock/${symbol}`;

        // Reset period buttons
        document.querySelectorAll('#bursa-detail-panel .period-btn').forEach(b => b.classList.remove('active'));
        const firstBtn = document.querySelector('#bursa-detail-panel .period-btn');
        if (firstBtn) firstBtn.classList.add('active');

        App.show('bursa-detail-panel');
        updateStarStates();
        loadDetail();
        App.$('bursa-detail-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function closeDetail() {
        App.hide('bursa-detail-panel');
        App.chart.destroy('bursaDetail');
    }

    function setDetailPeriod(period, btn) {
        App.state.bursa.detailPeriod = period;
        document.querySelectorAll('#bursa-detail-panel .period-btn').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        loadDetail();
    }

    async function loadDetail() {
        const sym = App.state.bursa.detailSymbol;
        if (!sym) return;

        try {
            const [q, c] = await Promise.all([
                App.api(`/api/bursa/quote/${sym}`),
                App.apiSilent(`/api/bursa/chart/${sym}?period=${App.state.bursa.detailPeriod}`),
            ]);

            if (q.price) {
                const sign = (q.change_pct || 0) >= 0 ? '+' : '';
                const dir  = (q.change_pct || 0) >= 0 ? 'up' : 'down';
                App.setText('bursa-detail-price', `MYR ${q.price.toFixed(3)}`);
                const changeEl = App.$('bursa-detail-change');
                changeEl.innerHTML = '';
                const sp = document.createElement('span');
                sp.className = dir;
                sp.textContent = `${sign}${(q.change_abs||0).toFixed(3)} (${sign}${(q.change_pct||0).toFixed(2)}%)`;
                changeEl.appendChild(sp);

                // Fundamentals
                const items = [
                    q.volume   ? `Vol: ${(q.volume/1e6).toFixed(1)}M`   : null,
                    q.day_high ? `H: ${q.day_high.toFixed(3)}`          : null,
                    q.day_low  ? `L: ${q.day_low.toFixed(3)}`           : null,
                    q.pe_ratio ? `P/E: ${q.pe_ratio.toFixed(1)}`        : null,
                    q.market_cap ? `Cap: ${(q.market_cap/1e9).toFixed(1)}B` : null,
                ].filter(Boolean);
                const fundsEl = App.$('bursa-chart-fundamentals');
                fundsEl.innerHTML = '';
                items.forEach(txt => {
                    const sp = document.createElement('span');
                    sp.className = 'bursa-fund-item';
                    sp.textContent = txt;
                    fundsEl.appendChild(sp);
                });
            }

            if (c && c.times?.length) {
                App.chart.priceLine('bursaDetail', 'bursa-price-chart', c.times, c.close);
            }
        } catch (err) {
            console.error('Bursa detail error:', err);
        }

        loadOrderBook(sym);
    }

    // ── Order Book ───────────────────────────────────────────────────────────

    async function loadOrderBook(symbol) {
        App.$('ob-loading').classList.remove('hidden');
        App.$('ob-content').classList.add('hidden');
        App.$('ob-error').classList.add('hidden');

        try {
            const data = await App.api(`/api/orderbook/${encodeURIComponent(symbol)}`);
            App.$('ob-loading').classList.add('hidden');

            // Source badge
            const badge = App.$('ob-source-badge');
            badge.textContent = data.level === 2 ? 'Level 2 \u00B7 Live' : 'Level 1 \u00B7 Delayed';
            badge.className = `ob-source-badge ${data.level === 2 ? 'ob-l2' : 'ob-l1'}`;

            // Pressure bar
            const pressure = data.pressure ?? 50;
            App.$('ob-pressure-fill').style.width = pressure + '%';
            App.setText('ob-bid-pct', pressure.toFixed(1) + '% buy');
            App.setText('ob-ask-pct', (100 - pressure).toFixed(1) + '% sell');

            // Spread
            const spreadEl = App.$('ob-spread');
            spreadEl.textContent = data.spread != null
                ? `Spread ${data.spread}${data.spread_pct != null ? ` (${data.spread_pct}%)` : ''}`
                : '';

            // Bid rows
            const bidsEl = App.$('ob-bids');
            bidsEl.innerHTML = '';
            (data.bids || []).forEach((b, i) => {
                const maxSize = Math.max(...(data.bids || []).map(x => x.size), 1);
                const barW = Math.round(b.size / maxSize * 100);
                const row = document.createElement('div');
                row.className = `ob-row ob-bid-row${i === 0 ? ' ob-top' : ''}`;
                row.style.setProperty('--bar', barW + '%');
                const sizeSpan = document.createElement('span');
                sizeSpan.className = 'ob-size';
                sizeSpan.textContent = b.size.toLocaleString();
                const priceSpan = document.createElement('span');
                priceSpan.className = 'ob-price up';
                priceSpan.textContent = b.price.toFixed(3);
                row.append(sizeSpan, priceSpan);
                bidsEl.appendChild(row);
            });

            // Ask rows
            const asksEl = App.$('ob-asks');
            asksEl.innerHTML = '';
            (data.asks || []).forEach((a, i) => {
                const maxSize = Math.max(...(data.asks || []).map(x => x.size), 1);
                const barW = Math.round(a.size / maxSize * 100);
                const row = document.createElement('div');
                row.className = `ob-row ob-ask-row${i === 0 ? ' ob-top' : ''}`;
                row.style.setProperty('--bar', barW + '%');
                const priceSpan = document.createElement('span');
                priceSpan.className = 'ob-price down';
                priceSpan.textContent = a.price.toFixed(3);
                const sizeSpan = document.createElement('span');
                sizeSpan.className = 'ob-size';
                sizeSpan.textContent = a.size.toLocaleString();
                row.append(priceSpan, sizeSpan);
                asksEl.appendChild(row);
            });

            App.$('ob-content').classList.remove('hidden');
        } catch (err) {
            App.$('ob-loading').classList.add('hidden');
            App.setText('ob-error', 'Failed to load order book');
            App.$('ob-error').classList.remove('hidden');
        }
    }

    // ── Stock Detail Modal ───────────────────────────────────────────────────

    function openStockModal(symbol) {
        const ms = App.state.modal;
        ms.symbol = symbol;
        ms.period = '1d';

        const link = App.$('sm-bursa-link');
        if (link) link.href = `/stock/${encodeURIComponent(symbol)}`;

        document.querySelectorAll('.sm-period').forEach(b => b.classList.remove('active'));
        const first = document.querySelector('.sm-period');
        if (first) first.classList.add('active');

        App.setText('sm-symbol', symbol.replace('.KL', ''));
        App.setText('sm-name', '');
        App.setText('sm-price', '\u2014');
        App.setText('sm-change', '');
        App.setText('sm-change-pct', '');
        App.setText('sm-range', '');
        App.setText('sm-vol', 'Vol: \u2014');
        App.setText('sm-high', 'H: \u2014');
        App.setText('sm-low', 'L: \u2014');

        App.$('stock-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        loadModalQuote(symbol);
        loadModalChart(symbol, '1d');
    }

    function closeStockModal(e) {
        if (e && e.target !== App.$('stock-modal')) return;
        App.$('stock-modal').classList.add('hidden');
        document.body.style.overflow = '';
    }

    function setModalPeriod(period, btn) {
        App.state.modal.period = period;
        document.querySelectorAll('.sm-period').forEach(b => b.classList.remove('active'));
        if (btn) btn.classList.add('active');
        if (App.state.modal.symbol) loadModalChart(App.state.modal.symbol, period);
    }

    async function loadModalQuote(symbol) {
        const d = await App.apiSilent(`/api/bursa/quote/${symbol}`);
        if (!d || !d.price) return;

        App.setText('sm-name', d.name || '');
        App.setText('sm-price', `MYR ${d.price.toFixed(2)}`);

        const chg = d.change_abs ?? 0;
        const pct = d.change_pct ?? 0;
        const up  = chg >= 0;

        const ce = App.$('sm-change');
        const cp = App.$('sm-change-pct');
        ce.textContent = `${up ? '+' : ''}${chg.toFixed(3)}`;
        cp.textContent = `(${up ? '+' : ''}${pct.toFixed(2)}%)`;
        ce.className = `sm-change ${up ? 'up' : 'down'}`;
        cp.className = `sm-change-pct ${up ? 'up' : 'down'}`;

        if (d.volume)   App.setText('sm-vol',  `Vol: ${(d.volume/1e6).toFixed(2)}M`);
        if (d.day_high) App.setText('sm-high', `H: ${d.day_high.toFixed(3)}`);
        if (d.day_low)  App.setText('sm-low',  `L: ${d.day_low.toFixed(3)}`);
        if (d.day_high && d.day_low)
            App.setText('sm-range', `Range ${d.day_low.toFixed(3)} \u2013 ${d.day_high.toFixed(3)}`);
    }

    async function loadModalChart(symbol, period) {
        const loading = App.$('sm-chart-loading');
        const canvas  = App.$('sm-chart');
        loading.classList.remove('hidden');
        canvas.classList.add('hidden');
        App.chart.destroy('stockModal');

        try {
            const d = await App.api(`/api/bursa/chart/${symbol}?period=${period}`);
            if (!d.times || !d.close) { loading.textContent = 'No data'; return; }
            loading.classList.add('hidden');
            canvas.classList.remove('hidden');

            App.chart.priceLine('stockModal', 'sm-chart', d.times, d.close, {}, [{
                id: 'crosshairLine',
                afterDraw(chart) {
                    const { ctx, chartArea, tooltip } = chart;
                    if (!tooltip._active || !tooltip._active.length) return;
                    const x = tooltip._active[0].element.x;
                    ctx.save();
                    ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom);
                    ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(255,255,255,0.15)'; ctx.setLineDash([4, 3]);
                    ctx.stroke(); ctx.restore();
                },
            }]);
        } catch {
            loading.textContent = 'Failed to load chart';
        }
    }

    function openNewTab() {
        if (!App.state.modal.symbol) return;
        window.open(`/?stock=${encodeURIComponent(App.state.modal.symbol)}`, '_blank', 'noopener,noreferrer');
    }

    // ── Prediction Accuracy ──────────────────────────────────────────────────

    async function loadAccuracy() {
        App.show('accuracy-loading-inline');
        App.hide('accuracy-empty');
        App.hide('accuracy-section');
        App.hide('accuracy-log');

        try {
            const data = await App.api('/api/bursa/accuracy');
            App.hide('accuracy-loading-inline');
            renderAccuracy(data);
        } catch (err) {
            App.hide('accuracy-loading-inline');
            App.toast(err.message, 'error');
        }
    }

    function renderAccuracy(data) {
        const s = data.summary;
        App.setText('acc-total', s.total);
        App.setText('acc-with-data', s.with_data);

        const accEl = App.$('acc-pct');
        accEl.innerHTML = '';
        if (s.accuracy_pct !== null) {
            const sp = document.createElement('span');
            sp.style.color = s.accuracy_pct >= 50 ? '#00c853' : '#ff1744';
            sp.textContent = `${s.accuracy_pct}%`;
            accEl.appendChild(sp);
        } else {
            const sp = document.createElement('span');
            sp.className = 'hint';
            sp.textContent = 'No data yet';
            accEl.appendChild(sp);
        }

        // Scatter chart
        const withData = data.predictions.filter(p => p.actual_return_pct !== null);
        const correct  = withData.filter(p => p.outcome === 'correct');
        const wrong    = withData.filter(p => p.outcome === 'wrong');

        App.chart.create('accuracyScatter', 'accuracy-scatter', {
            type: 'scatter',
            data: {
                datasets: [
                    { label: 'Correct', data: correct.map(p => ({ x: p.confidence * 100, y: p.actual_return_pct })), backgroundColor: '#00c85390', pointRadius: 6 },
                    { label: 'Wrong',   data: wrong.map(p => ({ x: p.confidence * 100, y: p.actual_return_pct })), backgroundColor: '#ff174490', pointRadius: 6 },
                ],
            },
            options: {
                responsive: true,
                scales: {
                    x: { title: { display: true, text: 'Predicted Confidence (%)', color: '#9aa0b0' }, ticks: { color: '#5f6477' }, grid: { color: '#1e2235' } },
                    y: { title: { display: true, text: 'Actual Return (%)', color: '#9aa0b0' }, ticks: { color: '#5f6477' }, grid: { color: '#1e2235' } },
                },
                plugins: {
                    legend: { labels: { color: '#9aa0b0' } },
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.dataset.label} | ${ctx.raw.x.toFixed(0)}% conf \u2192 ${ctx.raw.y > 0 ? '+' : ''}${ctx.raw.y.toFixed(2)}% actual`,
                        },
                    },
                },
            },
        });

        // Table — built with DOM methods
        const tbody = App.$('accuracy-table-body');
        tbody.innerHTML = '';
        const frag = document.createDocumentFragment();

        data.predictions.forEach(p => {
            const tr = document.createElement('tr');

            const tdSym = document.createElement('td');
            const strong = document.createElement('strong');
            strong.textContent = p.symbol;
            tdSym.appendChild(strong);

            const tdAction = document.createElement('td');
            const actionSpan = document.createElement('span');
            actionSpan.className = `action-${App.actionClass(p.action)}`;
            actionSpan.textContent = p.action;
            tdAction.appendChild(actionSpan);

            const tdConf = document.createElement('td');
            tdConf.textContent = `${((p.confidence||0)*100).toFixed(0)}%`;

            const tdEntry = document.createElement('td');
            tdEntry.textContent = p.entry_price ? p.entry_price.toFixed(3) : '\u2014';

            const tdLatest = document.createElement('td');
            tdLatest.textContent = p.latest_price ? p.latest_price.toFixed(3) : '\u2014';

            const tdReturn = document.createElement('td');
            if (p.actual_return_pct !== null) {
                const retSpan = document.createElement('span');
                retSpan.className = p.actual_return_pct >= 0 ? 'up' : 'down';
                retSpan.textContent = `${p.actual_return_pct >= 0 ? '+' : ''}${p.actual_return_pct.toFixed(2)}%`;
                tdReturn.appendChild(retSpan);
            } else {
                const pending = document.createElement('span');
                pending.className = 'hint';
                pending.textContent = 'pending';
                tdReturn.appendChild(pending);
            }

            const tdOutcome = document.createElement('td');
            if (p.outcome === 'correct') {
                const ok = document.createElement('span');
                ok.className = 'outcome-correct';
                ok.textContent = '\u2713 Correct';
                tdOutcome.appendChild(ok);
            } else if (p.outcome === 'wrong') {
                const no = document.createElement('span');
                no.className = 'outcome-wrong';
                no.textContent = '\u2717 Wrong';
                tdOutcome.appendChild(no);
            } else {
                const pend = document.createElement('span');
                pend.className = 'hint';
                pend.textContent = 'Pending';
                tdOutcome.appendChild(pend);
            }

            const tdDate = document.createElement('td');
            tdDate.className = 'hint';
            tdDate.textContent = (p.created_at || '').slice(0, 16);

            tr.append(tdSym, tdAction, tdConf, tdEntry, tdLatest, tdReturn, tdOutcome, tdDate);
            frag.appendChild(tr);
        });
        tbody.appendChild(frag);

        App.show('accuracy-section');
        App.show('accuracy-log');
    }

    // ── Watchlist ─────────────────────────────────────────────────────────────

    let _watchlistSymbols = new Set(); // fast lookup

    async function loadWatchlist() {
        try {
            const data = await App.api('/api/watchlist');
            const items = data.watchlist || [];
            _watchlistSymbols = new Set(items.map(i => i.symbol));
            renderWatchlist(items);
            updateStarStates();
            // Check alerts
            items.forEach(item => {
                if (item.alert_triggered === 'above') {
                    App.toast(`${item.name || item.symbol} hit alert: price MYR ${item.price?.toFixed(3)} \u2265 ${item.alert_above}`, 'warn', 'Price Alert \u25B2');
                } else if (item.alert_triggered === 'below') {
                    App.toast(`${item.name || item.symbol} hit alert: price MYR ${item.price?.toFixed(3)} \u2264 ${item.alert_below}`, 'warn', 'Price Alert \u25BC');
                }
            });
        } catch {
            // silent — watchlist is supplementary
        }
    }

    function renderWatchlist(items) {
        const section = App.$('watchlist-section');
        const rows = App.$('watchlist-rows');
        const empty = App.$('watchlist-empty');
        const countEl = App.$('watchlist-count');

        if (!items.length) {
            rows.innerHTML = '';
            App.show('watchlist-empty');
            if (countEl) countEl.textContent = '';
            section.classList.remove('hidden');
            return;
        }

        App.hide('watchlist-empty');
        if (countEl) countEl.textContent = `${items.length} stocks`;
        rows.innerHTML = '';
        const frag = document.createDocumentFragment();

        items.forEach(item => {
            const dir = (item.change_pct || 0) >= 0 ? 'up' : 'down';
            const sign = (item.change_pct || 0) >= 0 ? '+' : '';
            const hasAlert = item.alert_above || item.alert_below;
            const triggered = item.alert_triggered;

            const row = document.createElement('div');
            row.className = 'wl-row';
            row.dataset.symbol = item.symbol;

            // Star
            const star = document.createElement('button');
            star.className = 'wl-star starred';
            star.textContent = '\u2605';
            star.dataset.action = 'toggle-watchlist';
            star.dataset.arg = item.symbol;
            star.dataset.name = item.name || '';

            // Info
            const info = document.createElement('div');
            info.className = 'wl-info';
            const nameEl = document.createElement('span');
            nameEl.className = 'wl-name';
            nameEl.textContent = item.name || item.symbol;
            const symEl = document.createElement('span');
            symEl.className = 'wl-symbol';
            symEl.textContent = item.symbol.replace('.KL', '');
            info.append(nameEl, symEl);

            // Note
            const noteRow = document.createElement('div');
            noteRow.className = 'wl-note-row';
            const note = document.createElement('span');
            note.className = 'wl-note';
            note.textContent = item.note || '';
            note.dataset.action = 'watchlist-edit-note';
            note.dataset.arg = item.symbol;
            note.title = 'Click to edit note';
            noteRow.appendChild(note);
            info.appendChild(noteRow);

            // Price
            const priceCol = document.createElement('div');
            priceCol.className = 'wl-price-col';
            if (item.price) {
                const price = document.createElement('div');
                price.className = 'wl-price';
                price.textContent = `MYR ${item.price.toFixed(3)}`;
                const change = document.createElement('div');
                change.className = `wl-change ${dir}`;
                change.textContent = `${sign}${(item.change_pct || 0).toFixed(2)}%`;
                priceCol.append(price, change);
            } else {
                priceCol.textContent = '\u2014';
            }

            // Alert indicator
            const alertCol = document.createElement('div');
            alertCol.className = 'wl-alert-col';
            if (triggered) {
                const dot = document.createElement('span');
                dot.className = 'wl-alert-dot triggered';
                alertCol.appendChild(dot);
            } else if (hasAlert) {
                const dot = document.createElement('span');
                dot.className = 'wl-alert-dot set';
                alertCol.appendChild(dot);
            }
            const alertLabel = document.createElement('span');
            alertLabel.className = 'wl-alert-label';
            alertLabel.textContent = hasAlert
                ? `${item.alert_below ? '\u25BC' + item.alert_below : ''} ${item.alert_above ? '\u25B2' + item.alert_above : ''}`.trim()
                : 'Set alert';
            alertLabel.dataset.action = 'watchlist-set-alert';
            alertLabel.dataset.arg = item.symbol;
            alertLabel.title = 'Click to set price alert';
            alertCol.appendChild(alertLabel);

            // Actions
            const actions = document.createElement('div');
            actions.className = 'wl-actions';
            const analyzeBtn = document.createElement('button');
            analyzeBtn.className = 'wl-analyze-btn';
            analyzeBtn.textContent = 'Analyze';
            analyzeBtn.dataset.action = 'watchlist-analyze';
            analyzeBtn.dataset.arg = item.symbol;
            const detailBtn = document.createElement('button');
            detailBtn.className = 'wl-detail-btn';
            detailBtn.textContent = 'Detail';
            detailBtn.dataset.action = 'watchlist-detail';
            detailBtn.dataset.arg = item.symbol;
            detailBtn.dataset.name = item.name || '';
            actions.append(analyzeBtn, detailBtn);

            row.append(star, info, priceCol, alertCol, actions);
            frag.appendChild(row);
        });

        rows.appendChild(frag);
        section.classList.remove('hidden');
    }

    async function toggleWatchlist(symbol, name) {
        if (_watchlistSymbols.has(symbol)) {
            await App.api(`/api/watchlist/${encodeURIComponent(symbol)}`, { method: 'DELETE' });
            _watchlistSymbols.delete(symbol);
            App.toast(`${name || symbol} removed from watchlist`, 'info');
        } else {
            await App.api('/api/watchlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol, name }),
            });
            _watchlistSymbols.add(symbol);
            App.toast(`${name || symbol} added to watchlist`, 'success');
        }
        updateStarStates();
        loadWatchlist();
    }

    function updateStarStates() {
        // Update stars on industry stock rows
        document.querySelectorAll('.bi-stock-row .star-toggle').forEach(star => {
            const sym = star.dataset.sym;
            star.textContent = _watchlistSymbols.has(sym) ? '\u2605' : '\u2606';
            star.classList.toggle('starred', _watchlistSymbols.has(sym));
        });
        // Update detail panel star
        const detailStar = App.$('detail-star-btn');
        if (detailStar && App.state.bursa.detailSymbol) {
            const inWl = _watchlistSymbols.has(App.state.bursa.detailSymbol);
            detailStar.textContent = inWl ? '\u2605' : '\u2606';
            detailStar.classList.toggle('starred', inWl);
        }
    }

    async function editNote(symbol) {
        const row = document.querySelector(`.wl-row[data-symbol="${symbol}"]`);
        if (!row) return;
        const noteEl = row.querySelector('.wl-note');
        const current = noteEl.textContent || '';

        // Replace with input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'wl-note-input';
        input.value = current;
        input.placeholder = 'Add a note...';
        noteEl.replaceWith(input);
        input.focus();
        input.select();

        const save = async () => {
            const val = input.value.trim();
            await App.apiSilent(`/api/watchlist/${encodeURIComponent(symbol)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: val }),
            });
            const newNote = document.createElement('span');
            newNote.className = 'wl-note';
            newNote.textContent = val;
            newNote.dataset.action = 'watchlist-edit-note';
            newNote.dataset.arg = symbol;
            newNote.title = 'Click to edit note';
            input.replaceWith(newNote);
        };

        input.addEventListener('blur', save);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
    }

    function showAlertEditor(symbol) {
        // Remove existing editor
        document.querySelectorAll('.wl-alert-edit').forEach(e => e.remove());

        const row = document.querySelector(`.wl-row[data-symbol="${symbol}"]`);
        if (!row) return;
        const alertCol = row.querySelector('.wl-alert-col');

        const editor = document.createElement('div');
        editor.className = 'wl-alert-edit';

        const aboveInput = document.createElement('input');
        aboveInput.type = 'number';
        aboveInput.className = 'wl-alert-input';
        aboveInput.placeholder = 'Above';
        aboveInput.step = '0.001';

        const belowInput = document.createElement('input');
        belowInput.type = 'number';
        belowInput.className = 'wl-alert-input';
        belowInput.placeholder = 'Below';
        belowInput.step = '0.001';

        const saveBtn = document.createElement('button');
        saveBtn.className = 'wl-alert-save';
        saveBtn.textContent = 'Set';
        saveBtn.addEventListener('click', async () => {
            const above = parseFloat(aboveInput.value) || 0;
            const below = parseFloat(belowInput.value) || 0;
            await App.apiSilent(`/api/watchlist/${encodeURIComponent(symbol)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ alert_above: above, alert_below: below }),
            });
            editor.remove();
            loadWatchlist();
            App.toast('Alert updated', 'success');
        });

        editor.append(belowInput, aboveInput, saveBtn);
        alertCol.style.position = 'relative';
        alertCol.appendChild(editor);

        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', function close(e) {
                if (!editor.contains(e.target) && e.target !== alertCol.querySelector('.wl-alert-label')) {
                    editor.remove();
                    document.removeEventListener('click', close);
                }
            });
        }, 100);
    }

    // Add star toggles to industry stock rows
    const _origRenderIndustries = renderIndustries;
    renderIndustries = function(industries) {
        _origRenderIndustries(industries);
        // Inject star toggles into each stock row
        document.querySelectorAll('.bi-stock-row[data-sym]').forEach(row => {
            const sym = row.dataset.sym;
            const star = document.createElement('span');
            star.className = `star-toggle ${_watchlistSymbols.has(sym) ? 'starred' : ''}`;
            star.dataset.sym = sym;
            star.dataset.name = row.dataset.name || '';
            star.textContent = _watchlistSymbols.has(sym) ? '\u2605' : '\u2606';
            star.addEventListener('click', e => {
                e.stopPropagation();
                toggleWatchlist(sym, row.dataset.name);
            });
            row.querySelector('.bi-stock-left').prepend(star);
        });
    };

    // ── Public API ───────────────────────────────────────────────────────────
    function toggleAutoRefresh() {
        const state = App.state.bursa;
        state.autoRefresh = !state.autoRefresh;
        const btn = App.$('bursa-auto-refresh-btn');
        if (btn) {
            btn.textContent = state.autoRefresh ? 'Auto \u25cf' : 'Auto \u25cb';
            btn.className = state.autoRefresh ? 'btn-sm btn-sm-active' : 'btn-sm btn-sm-outline';
        }
        if (!state.autoRefresh && state.refreshTimer) {
            clearTimeout(state.refreshTimer);
            state.refreshTimer = null;
        }
        if (state.autoRefresh && isBursaOpen()) {
            state.refreshTimer = setTimeout(() => loadMarket(true), REFRESH_MS);
        }
        App.toast(state.autoRefresh ? 'Auto-refresh ON (30s)' : 'Auto-refresh OFF', 'info');
    }

    App.tabs.bursa = {
        loadMarket, loadAccuracy, loadWatchlist,
        openDetail, closeDetail, setDetailPeriod,
        openStockModal, closeStockModal, setModalPeriod, openNewTab,
        toggleWatchlist, editNote, showAlertEditor, toggleAutoRefresh,
    };

    // Handle ?stock=SYMBOL param
    const urlParam = new URLSearchParams(window.location.search).get('stock');
    if (urlParam) {
        window.addEventListener('load', () => {
            setTimeout(() => openStockModal(decodeURIComponent(urlParam)), 300);
        });
    }
})();
