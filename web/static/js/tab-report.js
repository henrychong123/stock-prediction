/* ===== tab-report.js — Daily Prediction Report tab ===== */

(function () {
    let _reportData = [];  // full dataset for filtering

    // Build industry filter options from config
    function initFilters() {
        const select = App.$('report-filter-industry');
        if (!select || select.options.length > 1) return;
        // Industries will be populated from data
    }

    async function load() {
        App.show('report-loading');
        App.hide('report-table-wrap');
        App.hide('report-empty');
        App.hide('report-status');

        try {
            // Fetch latest predictions + industry data in parallel
            const [predData, indData] = await Promise.all([
                App.api('/api/predictions/latest'),
                App.apiSilent('/api/bursa/industries'),
            ]);

            App.hide('report-loading');
            const preds = predData.predictions || {};
            const industries = indData?.industries || [];

            if (Object.keys(preds).length === 0) {
                App.show('report-empty');
                return;
            }

            // Build flat list with industry info
            _reportData = [];
            const industrySet = new Set();

            industries.forEach(ind => {
                ind.stocks.forEach(stock => {
                    const pred = preds[stock.symbol];
                    industrySet.add(ind.industry);
                    _reportData.push({
                        symbol: stock.symbol,
                        name: stock.name,
                        industry: ind.industry,
                        price: stock.price,
                        change_pct: stock.change_pct,
                        action: pred?.action || null,
                        confidence: pred?.confidence || 0,
                        score: pred?.score || 0,
                        created_at: pred?.created_at || null,
                    });
                });
            });

            // Sort by score (strongest buy first)
            _reportData.sort((a, b) => (b.score || 0) - (a.score || 0));

            // Populate industry filter
            const indSelect = App.$('report-filter-industry');
            if (indSelect && indSelect.options.length <= 1) {
                [...industrySet].sort().forEach(ind => {
                    const opt = document.createElement('option');
                    opt.value = ind;
                    opt.textContent = ind;
                    indSelect.appendChild(opt);
                });
            }

            renderReport();
            renderSummary();
        } catch (err) {
            App.hide('report-loading');
            App.toast(err.message, 'error');
        }
    }

    function getFilters() {
        return {
            action: App.$('report-filter-action')?.value || '',
            industry: App.$('report-filter-industry')?.value || '',
            minConfidence: parseInt(App.$('report-filter-confidence')?.value || '0') / 100,
        };
    }

    function renderReport() {
        const filters = getFilters();
        const tbody = App.$('report-tbody');
        if (!tbody) return;

        let filtered = _reportData.filter(r => r.action); // only stocks with predictions

        if (filters.action) filtered = filtered.filter(r => r.action === filters.action);
        if (filters.industry) filtered = filtered.filter(r => r.industry === filters.industry);
        if (filters.minConfidence > 0) filtered = filtered.filter(r => r.confidence >= filters.minConfidence);

        tbody.innerHTML = '';
        const frag = document.createDocumentFragment();

        filtered.forEach(r => {
            const tr = document.createElement('tr');
            tr.className = `report-row action-row-${App.actionClass(r.action)}`;
            tr.dataset.symbol = r.symbol;

            const dir = (r.change_pct || 0) >= 0 ? 'up' : 'down';
            const sign = (r.change_pct || 0) >= 0 ? '+' : '';
            const confPct = (r.confidence * 100).toFixed(0);
            const scoreStr = r.score >= 0 ? `+${r.score.toFixed(3)}` : r.score.toFixed(3);
            const ago = r.created_at ? App.timeAgo(r.created_at) : '\u2014';

            tr.innerHTML = `
                <td>
                    <div class="report-stock-name">${App.esc(r.name)}</div>
                    <div class="report-stock-code">${App.esc(r.symbol.replace('.KL', ''))}</div>
                </td>
                <td><span class="report-industry-tag">${App.esc(r.industry)}</span></td>
                <td>${r.price ? `MYR ${r.price.toFixed(3)}` : '\u2014'}</td>
                <td><span class="${dir}">${sign}${(r.change_pct || 0).toFixed(2)}%</span></td>
                <td><span class="bi-pred-badge action-${App.actionClass(r.action)}">${App.esc(r.action)}</span></td>
                <td>${confPct}%</td>
                <td><span style="color:${r.score > 0 ? '#00c853' : r.score < 0 ? '#ff1744' : '#ffc107'}">${scoreStr}</span></td>
                <td class="hint">${ago}</td>
            `;

            // Click to analyze
            tr.addEventListener('click', () => {
                document.querySelector('[data-tab="stocks-tab"]')?.click();
                App.tabs.analysis.switchMarket('MY');
                App.tabs.analysis.quickAnalyze(r.symbol);
            });

            frag.appendChild(tr);
        });

        tbody.appendChild(frag);
        App.show('report-table-wrap');

        // Update count
        const status = App.$('report-status');
        if (status) {
            status.textContent = `Showing ${filtered.length} of ${_reportData.filter(r => r.action).length} stocks with predictions`;
            status.classList.remove('hidden');
        }
    }

    function renderSummary() {
        const summary = App.$('report-summary');
        if (!summary) return;

        const withPreds = _reportData.filter(r => r.action);
        const counts = {};
        withPreds.forEach(r => { counts[r.action] = (counts[r.action] || 0) + 1; });

        const order = ['STRONG BUY', 'BUY', 'HOLD', 'SELL', 'STRONG SELL'];
        summary.innerHTML = '';
        const frag = document.createDocumentFragment();

        order.forEach(action => {
            if (!counts[action]) return;
            const div = document.createElement('div');
            div.className = `report-summary-item action-${App.actionClass(action)}`;

            const count = document.createElement('span');
            count.className = 'report-summary-count';
            count.textContent = counts[action];

            const label = document.createElement('span');
            label.className = 'report-summary-label';
            label.textContent = action;

            div.append(count, label);
            frag.appendChild(div);
        });

        const total = document.createElement('div');
        total.className = 'report-summary-item report-summary-total';
        total.innerHTML = `<span class="report-summary-count">${withPreds.length}</span><span class="report-summary-label">Total</span>`;
        frag.appendChild(total);

        summary.appendChild(frag);
    }

    async function runBatch() {
        const btn = document.querySelector('[data-action="run-batch-predict"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }

        App.toast('Batch analysis started \u2014 this may take several minutes', 'info', 'Batch Analysis');

        await App.apiSilent('/api/batch-predict', { method: 'POST' });

        // Poll for completion every 30 seconds
        const poll = setInterval(async () => {
            const data = await App.apiSilent('/api/predictions/latest');
            if (data && Object.keys(data.predictions || {}).length > 0) {
                clearInterval(poll);
                if (btn) { btn.disabled = false; btn.textContent = '\u25A4 Run Batch Analysis'; }
                App.toast('Batch analysis complete!', 'success');
                load();
            }
        }, 30000);

        // Timeout after 30 minutes
        setTimeout(() => {
            clearInterval(poll);
            if (btn) { btn.disabled = false; btn.textContent = '\u25A4 Run Batch Analysis'; }
        }, 30 * 60 * 1000);
    }

    // Filter event listeners
    function setupFilters() {
        App.$('report-filter-action')?.addEventListener('change', renderReport);
        App.$('report-filter-industry')?.addEventListener('change', renderReport);
        const confSlider = App.$('report-filter-confidence');
        if (confSlider) {
            confSlider.addEventListener('input', () => {
                App.setText('report-conf-label', `Min: ${confSlider.value}%`);
                renderReport();
            });
        }
    }

    setupFilters();

    App.tabs.report = { load, runBatch };
})();
