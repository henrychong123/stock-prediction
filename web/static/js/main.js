/* ===== main.js — Tab router, event delegation, init ===== */

(function () {
    // ── Clock ────────────────────────────────────────────────────────────────
    function updateClock() {
        App.setText('clock', new Date().toLocaleString('en-US', {
            weekday: 'short', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        }));
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── Tab System (with ARIA) ───────────────────────────────────────────────
    const tabs     = document.querySelectorAll('.tab');
    const contents = document.querySelectorAll('.tab-content');

    function switchTab(target) {
        tabs.forEach(t => {
            const active = t === target;
            t.classList.toggle('active', active);
            t.setAttribute('aria-selected', active);
        });
        contents.forEach(c => c.classList.remove('active'));
        const panel = App.$(target.dataset.tab);
        if (panel) panel.classList.add('active');
    }

    tabs.forEach(tab => {
        tab.setAttribute('role', 'tab');
        tab.setAttribute('aria-selected', tab.classList.contains('active'));
        tab.setAttribute('aria-controls', tab.dataset.tab);
        tab.addEventListener('click', () => switchTab(tab));
    });

    contents.forEach(panel => {
        panel.setAttribute('role', 'tabpanel');
    });

    // ── Reparent old content into new tab wrappers ─────────────────────────
    function reparent(sourceId, targetId) {
        const source = App.$(sourceId);
        const target = App.$(targetId);
        if (source && target) {
            while (source.firstChild) target.appendChild(source.firstChild);
        }
    }

    // Move old tab content into new wrapper tabs
    reparent('stock-tab', 'stocks-analysis-section');
    reparent('bursa-tab', 'stocks-market-section');
    reparent('sector-tab', 'home-section-sectors');
    reparent('report-tab', 'home-section-report');
    reparent('trends-tab', 'home-section-trends');
    reparent('model-tab', 'settings-tab');

    // ── Lazy Tab Loading (5 new tabs) ───────────────────────────────────────
    const loaded = { home: false, stocks: false, news: false, catalyst: false, settings: false };

    document.querySelector('[data-tab="home-tab"]').addEventListener('click', () => {
        if (App.tabs.home) App.tabs.home.activate();
    });

    document.querySelector('[data-tab="stocks-tab"]').addEventListener('click', () => {
        if (!loaded.stocks && App.tabs.stocks) {
            loaded.stocks = true;
            App.tabs.stocks.initialize();
        }
        // Set up view toggle buttons
        document.querySelectorAll('.stocks-view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (App.tabs.stocks) App.tabs.stocks.switchView(btn.dataset.view);
                document.querySelectorAll('.stocks-view-btn').forEach(b => b.classList.toggle('active', b === btn));
            });
        });
    });

    document.querySelector('[data-tab="catalyst-tab"]').addEventListener('click', () => {
        if (App.tabs['catalyst-tab'] && App.tabs['catalyst-tab'].activate) {
            App.tabs['catalyst-tab'].activate();
        }
    });

    document.querySelector('[data-tab="newshub-tab"]').addEventListener('click', () => {
        App.tabs.news.startPoller();
        if (!loaded.news) { loaded.news = true; App.tabs.news.loadIndustryAnalysis(); }
    });

    document.querySelector('[data-tab="settings-tab"]').addEventListener('click', () => {
        if (App.tabs.settings) App.tabs.settings.load();
    });

    // Trigger Home tab on initial load
    if (App.tabs.home) App.tabs.home.activate();

    // ── Event Delegation (replaces all inline onclick handlers) ──────────────
    document.body.addEventListener('click', e => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const action = btn.dataset.action;
        const arg    = btn.dataset.arg;

        switch (action) {
            // Analysis tab
            case 'switch-market':    App.tabs.analysis.switchMarket(arg); break;
            case 'quick-analyze':    App.tabs.analysis.quickAnalyze(arg); break;
            case 'analyze':          App.tabs.analysis.analyze(); break;
            case 'signals-view-tab': {
                const view = btn.dataset.signalsView;
                document.querySelectorAll('.signals-tab').forEach(t => t.classList.toggle('active', t.dataset.signalsView === view));
                document.querySelectorAll('.signals-view').forEach(v => {
                    v.classList.toggle('hidden', v.id !== `signals-view-${view}`);
                });
                // Re-render the chart fresh into the now-visible container
                // This avoids resize artifacts and blurriness
                setTimeout(() => {
                    if (view === 'weights' && App.tabs.analysis._rerenderWeights) {
                        App.tabs.analysis._rerenderWeights();
                    } else if (view === 'radar' && App.tabs.analysis._rerenderRadar) {
                        App.tabs.analysis._rerenderRadar();
                    }
                }, 30);
                break;
            }
            case 'set-analysis-mode': {
                const mode = btn.dataset.mode;
                App.$('full-mode-toggle').value = mode;
                document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
                break;
            }

            // Sectors tab
            case 'load-sectors':     App.tabs.sectors.load(); break;

            // News tab
            case 'news-range':       App.tabs.news.setRange(arg ? Number(arg) : null, btn); break;
            case 'fetch-all-news':   App.tabs.news.fetchAll(); break;

            // Trends tab
            case 'load-trend':       App.tabs.trends.loadTrend(); break;
            case 'go-analyze':       App.tabs.trends.goAnalyze(); break;
            case 'load-sector-history': App.tabs.trends.loadSectorHistory(); break;

            // Bursa tab
            case 'refresh-bursa':    App.tabs.bursa.loadMarket(true); break;
            case 'toggle-bursa-auto-refresh': App.tabs.bursa.toggleAutoRefresh(); break;
            case 'load-accuracy':    App.tabs.bursa.loadAccuracy(); break;
            case 'bursa-period':     App.tabs.bursa.setDetailPeriod(arg, btn); break;
            case 'close-detail':     App.tabs.bursa.closeDetail(); break;
            case 'close-modal':      App.tabs.bursa.closeStockModal(e); break;
            case 'sm-period':        App.tabs.bursa.setModalPeriod(arg, btn); break;

            // Report tab
            case 'run-batch-predict': App.tabs.report.runBatch(); break;

            // Catalyst
            case 'catalyst-scan':
                if (App.actions && App.actions['catalyst-scan']) App.actions['catalyst-scan']();
                break;

            // Watchlist
            case 'toggle-watchlist': App.tabs.bursa.toggleWatchlist(
                arg || App.state.bursa.detailSymbol,
                btn.dataset.name || App.$('bursa-detail-name')?.textContent || ''
            ); break;
            case 'watchlist-analyze': {
                // Switch to Analysis tab and analyze
                document.querySelector('[data-tab="stock-tab"]').click();
                App.tabs.analysis.switchMarket('MY');
                App.tabs.analysis.quickAnalyze(arg);
                break;
            }
            case 'watchlist-detail':  App.tabs.bursa.openDetail(arg, btn.dataset.name || ''); break;
            case 'watchlist-edit-note': App.tabs.bursa.editNote(arg); break;
            case 'watchlist-set-alert': App.tabs.bursa.showAlertEditor(arg); break;
            case 'toggle-watchlist-collapse': {
                const body = App.$('watchlist-body');
                const collapsed = body.classList.toggle('hidden');
                btn.textContent = collapsed ? '\u25B8' : '\u25BE';
                break;
            }
        }
    });

    // ── Keyboard Shortcuts ───────────────────────────────────────────────────
    App.$('symbol-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') App.tabs.analysis.analyze();
    });

    App.$('trend-symbol-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') App.tabs.trends.loadTrend();
    });

    // Escape closes stock modal
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') App.tabs.bursa.closeStockModal();
    });

    // Stock modal overlay click-to-close
    const modal = App.$('stock-modal');
    if (modal) {
        modal.addEventListener('click', e => {
            if (e.target === modal) App.tabs.bursa.closeStockModal();
        });
    }

    // ── Trends Visibility Check ──────────────────────────────────────────────
    (async function () {
        try {
            const data = await App.apiSilent('/api/predictions/history?limit=5');
            if (!data) return;
            const count = (data.predictions || []).length;
            const trendsTab = document.querySelector('[data-tab="trends-tab"]');
            if (count < 5) {
                trendsTab.style.opacity = '0.4';
                trendsTab.title = `Trends available after 5+ predictions (${count} so far)`;
                trendsTab.addEventListener('click', () => {
                    if (count < 5) App.toast(`Run ${5 - count} more analyses to unlock Trends`, 'info', 'Trends Locked');
                }, { capture: true });
            }
        } catch {}
    })();
})();
