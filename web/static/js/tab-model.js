/* ===== tab-model.js — AI Model Info tab ===== */

(function () {

    async function load() {
        App.show('model-loading');
        App.hide('model-content');

        try {
            const data = await App.api('/api/model-info');
            App.hide('model-loading');
            renderMetrics(data.metrics);
            renderFeatureImportance(data.feature_importance || []);
            renderWeights(data.weights);
            renderFeatureCategories(data.feature_categories || []);
            renderDataStats(data.data);
            App.show('model-content');
        } catch (err) {
            App.hide('model-loading');
            App.toast(err.message, 'error');
        }
    }

    function renderMetrics(metrics) {
        const grid = App.$('model-metrics');
        if (!grid || !metrics) return;
        grid.innerHTML = '';

        const dir = metrics.direction || {};
        const mag = metrics.magnitude || {};
        const items = [
            { label: 'Ensemble Accuracy', value: `${((dir.ensemble_accuracy || 0) * 100).toFixed(1)}%`, color: (dir.ensemble_accuracy || 0) > 0.5 ? 'green' : 'yellow' },
            { label: 'XGBoost Accuracy', value: `${((dir.xgb_accuracy || 0) * 100).toFixed(1)}%`, color: '' },
            { label: 'LightGBM Accuracy', value: `${((dir.lgbm_accuracy || 0) * 100).toFixed(1)}%`, color: '' },
            { label: 'Ensemble F1', value: `${((dir.ensemble_f1 || 0) * 100).toFixed(1)}%`, color: '' },
            { label: 'Magnitude MAE', value: `${(mag.mae || 0).toFixed(2)}%`, color: '' },
            { label: 'R\u00B2 Score', value: `${(mag.r2 || 0).toFixed(3)}`, color: '' },
            { label: 'Training Samples', value: (metrics.total_samples || 0).toLocaleString(), color: '' },
            { label: 'Stocks', value: (metrics.stocks || 0).toString(), color: '' },
            { label: 'Trained', value: metrics.trained_at ? metrics.trained_at.split('T')[0] : '\u2014', color: '' },
        ];

        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'model-metric-card';
            const label = document.createElement('div');
            label.className = 'model-metric-label';
            label.textContent = item.label;
            const value = document.createElement('div');
            value.className = `model-metric-value ${item.color}`;
            value.textContent = item.value;
            card.append(label, value);
            grid.appendChild(card);
        });
    }

    function renderFeatureImportance(features) {
        if (!features.length) return;

        const top20 = features.slice(0, 20);
        const labels = top20.map(f => f.feature.replace(/_/g, ' '));
        const values = top20.map(f => (f.importance * 100).toFixed(2));
        const colors = top20.map((f, i) => {
            if (i < 3) return '#00c853';
            if (i < 7) return '#69f0ae';
            if (i < 12) return '#ffc107';
            return '#9aa0b0';
        });

        App.chart.create('featureImportance', 'feature-importance-chart', {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'Importance %',
                    data: values,
                    backgroundColor: colors,
                    borderRadius: 4,
                    borderWidth: 0,
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: '#1e2235' }, ticks: { callback: v => v + '%' } },
                    y: { grid: { display: false }, ticks: { font: { size: 11 } } },
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    function renderWeights(weights) {
        const grid = App.$('model-weights');
        if (!grid || !weights) return;
        grid.innerHTML = '';

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

        ['US', 'MY'].forEach(market => {
            const mkt = weights[market];
            if (!mkt || !mkt.weights) return;

            const card = document.createElement('div');
            card.className = 'card model-weight-card';

            const header = document.createElement('div');
            header.className = 'model-weight-header';
            header.innerHTML = `<strong>${market === 'US' ? 'US Market' : 'Bursa Malaysia'}</strong>
                <span class="model-weight-source ${mkt.source === 'ai_optimized' ? 'optimized' : 'default'}">${mkt.source === 'ai_optimized' ? 'AI-Optimized' : 'Default'}</span>`;

            const bars = document.createElement('div');
            bars.className = 'model-weight-bars';

            const sorted = Object.entries(mkt.weights).sort((a, b) => b[1] - a[1]);
            sorted.forEach(([key, val]) => {
                const row = document.createElement('div');
                row.className = 'model-weight-row';
                const label = document.createElement('span');
                label.className = 'model-weight-label';
                label.textContent = weightLabels[key] || key;
                const barWrap = document.createElement('div');
                barWrap.className = 'model-weight-bar-wrap';
                const bar = document.createElement('div');
                bar.className = 'model-weight-bar';
                bar.style.width = `${(val * 100).toFixed(0)}%`;
                bar.style.background = weightColors[key] || '#888';
                barWrap.appendChild(bar);
                const pct = document.createElement('span');
                pct.className = 'model-weight-pct';
                pct.textContent = `${(val * 100).toFixed(1)}%`;
                row.append(label, barWrap, pct);
                bars.appendChild(row);
            });

            if (mkt.accuracy_before != null && mkt.accuracy_after != null) {
                const improvement = document.createElement('div');
                improvement.className = 'model-weight-improvement';
                const diff = ((mkt.accuracy_after - mkt.accuracy_before) * 100).toFixed(1);
                improvement.textContent = `Optimization: ${(mkt.accuracy_before * 100).toFixed(1)}% \u2192 ${(mkt.accuracy_after * 100).toFixed(1)}% (+${diff}%)`;
                bars.appendChild(improvement);
            }

            card.append(header, bars);
            grid.appendChild(card);
        });
    }

    function renderFeatureCategories(categories) {
        const tbody = App.$('model-features-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        let totalCount = 0;
        categories.forEach(cat => {
            totalCount += cat.count;
            const tr = document.createElement('tr');

            const tdName = document.createElement('td');
            tdName.innerHTML = `<strong>${App.esc(cat.name)}</strong>`;

            const tdFeatures = document.createElement('td');
            tdFeatures.className = 'model-features-list';
            tdFeatures.textContent = cat.features.join(', ');

            const tdSource = document.createElement('td');
            const badge = document.createElement('span');
            badge.className = 'model-source-badge';
            badge.textContent = cat.source;
            tdSource.appendChild(badge);

            const tdCount = document.createElement('td');
            tdCount.textContent = cat.count;

            tr.append(tdName, tdFeatures, tdSource, tdCount);
            tbody.appendChild(tr);
        });

        App.setText('model-total-features', totalCount);
    }

    function renderDataStats(data) {
        const grid = App.$('model-data-stats');
        if (!grid || !data) return;
        grid.innerHTML = '';

        const items = [
            { label: 'Training Rows', value: (data.training_rows || 0).toLocaleString(), icon: '\u25A4' },
            { label: 'Stocks', value: (data.stocks || 0).toString(), icon: '\u25C6' },
            { label: 'Date Range', value: data.date_range || '\u2014', icon: '\u25CB' },
            { label: 'Daily Features', value: (data.daily_features_rows || 0).toLocaleString(), icon: '\u25CE' },
            { label: 'GDELT Records', value: (data.gdelt_rows || 0).toLocaleString(), icon: '\u25C8' },
            { label: 'Earnings Records', value: (data.earnings_rows || 0).toLocaleString(), icon: '\u25B2' },
        ];

        items.forEach(item => {
            const card = document.createElement('div');
            card.className = 'model-data-card';
            card.innerHTML = `<span class="model-data-icon">${item.icon}</span>
                <div class="model-data-label">${item.label}</div>
                <div class="model-data-value">${item.value}</div>`;
            grid.appendChild(card);
        });
    }

    App.tabs.model = { load };
})();
