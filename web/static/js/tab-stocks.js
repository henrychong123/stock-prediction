/**
 * tab-stocks.js — Unified Stocks tab (merges Analysis + Bursa)
 *
 * Delegates to the existing tab-analysis.js and tab-bursa.js modules.
 * Provides a unified namespace: App.tabs.stocks
 */
(function () {
    "use strict";

    let _initialized = false;
    let _activeView = "analysis"; // "analysis" or "market"

    function initialize() {
        if (_initialized) return;
        _initialized = true;

        // Load Bursa market data on first access
        if (App.tabs.bursa) {
            App.tabs.bursa.loadWatchlist();
            App.tabs.bursa.loadMarket();
        }
    }

    function switchView(view) {
        _activeView = view;

        // Toggle sections
        const analysisSection = App.$("stocks-analysis-section");
        const marketSection = App.$("stocks-market-section");

        if (analysisSection) analysisSection.classList.toggle("hidden", view !== "analysis");
        if (marketSection) marketSection.classList.toggle("hidden", view !== "market");

        // Update view toggle buttons
        document.querySelectorAll(".stocks-view-btn").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.view === view);
        });

        // Load data if needed
        if (view === "market" && App.tabs.bursa) {
            App.tabs.bursa.loadWatchlist();
        }
    }

    // ── Delegated Analysis Functions ─────────────────────────────────────

    function switchMarket(market) {
        if (App.tabs.analysis) App.tabs.analysis.switchMarket(market);
    }

    function quickAnalyze(symbol) {
        switchView("analysis");
        if (App.tabs.analysis) App.tabs.analysis.quickAnalyze(symbol);
    }

    function analyze() {
        switchView("analysis");
        if (App.tabs.analysis) App.tabs.analysis.analyze();
    }

    function _rerenderRadar() {
        if (App.tabs.analysis && App.tabs.analysis._rerenderRadar) App.tabs.analysis._rerenderRadar();
    }

    function _rerenderWeights() {
        if (App.tabs.analysis && App.tabs.analysis._rerenderWeights) App.tabs.analysis._rerenderWeights();
    }

    // ── Delegated Bursa Functions ────────────────────────────────────────

    function loadMarket(force) {
        if (App.tabs.bursa) App.tabs.bursa.loadMarket(force);
    }
    function loadAccuracy() {
        if (App.tabs.bursa) App.tabs.bursa.loadAccuracy();
    }
    function loadWatchlist() {
        if (App.tabs.bursa) App.tabs.bursa.loadWatchlist();
    }
    function openDetail(sym, name) {
        if (App.tabs.bursa) App.tabs.bursa.openDetail(sym, name);
    }
    function closeDetail() {
        if (App.tabs.bursa) App.tabs.bursa.closeDetail();
    }
    function setDetailPeriod(period, btn) {
        if (App.tabs.bursa) App.tabs.bursa.setDetailPeriod(period, btn);
    }
    function openStockModal(sym) {
        if (App.tabs.bursa) App.tabs.bursa.openStockModal(sym);
    }
    function closeStockModal(e) {
        if (App.tabs.bursa) App.tabs.bursa.closeStockModal(e);
    }
    function setModalPeriod(period, btn) {
        if (App.tabs.bursa) App.tabs.bursa.setModalPeriod(period, btn);
    }
    function openNewTab() {
        if (App.tabs.bursa) App.tabs.bursa.openNewTab();
    }
    function toggleWatchlist(sym, name) {
        if (App.tabs.bursa) App.tabs.bursa.toggleWatchlist(sym, name);
    }
    function editNote(sym) {
        if (App.tabs.bursa) App.tabs.bursa.editNote(sym);
    }
    function showAlertEditor(sym) {
        if (App.tabs.bursa) App.tabs.bursa.showAlertEditor(sym);
    }
    function toggleAutoRefresh() {
        if (App.tabs.bursa) App.tabs.bursa.toggleAutoRefresh();
    }

    // Register unified namespace
    App.tabs.stocks = {
        initialize, switchView,
        // Analysis
        switchMarket, quickAnalyze, analyze, _rerenderRadar, _rerenderWeights,
        // Bursa
        loadMarket, loadAccuracy, loadWatchlist,
        openDetail, closeDetail, setDetailPeriod,
        openStockModal, closeStockModal, setModalPeriod, openNewTab,
        toggleWatchlist, editNote, showAlertEditor, toggleAutoRefresh,
    };
})();
