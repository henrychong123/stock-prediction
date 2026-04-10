/**
 * tab-home.js — Home dashboard tab (merges Sectors + Report + Trends)
 *
 * Shows at-a-glance: market overview, sector heatmap, daily report rankings,
 * prediction trends, active catalyst alerts summary.
 *
 * Uses sub-sections toggled via internal navigation.
 */
(function () {
    "use strict";

    let _initialized = false;
    let _activeSection = "overview";

    // ── Overview Section (default landing) ──────────────────────────────

    async function loadOverview() {
        // Load sector heatmap + report summary + latest catalyst in parallel
        await Promise.all([
            loadSectorsCompact(),
            loadReportSummary(),
            loadCatalystSummary(),
        ]);
    }

    async function loadSectorsCompact() {
        const el = App.$("home-sectors");
        if (!el) return;

        const cacheKey = `sectors_${App.state.market}`;
        const cached = App.cacheGet(cacheKey);

        try {
            const data = cached || await App.api(`/api/sectors?market=${App.state.market}`);
            if (!cached) App.cacheSet(cacheKey, data);
            const sectors = data.sectors || [];

            // Compact heatmap — bar chart only
            App.chart.create("homeSectorBar", "home-sector-chart", {
                type: "bar",
                data: {
                    labels: sectors.map(s => s.name),
                    datasets: [{
                        label: "Score",
                        data: sectors.map(s => s.score),
                        backgroundColor: sectors.map(s => s.score > 0.15 ? "#00c853" : s.score < -0.15 ? "#ff1744" : "#ffc107"),
                        borderRadius: 4,
                        borderWidth: 0,
                    }],
                },
                options: {
                    indexAxis: "y", responsive: true, maintainAspectRatio: false,
                    scales: {
                        x: { grid: { color: "#1e2235" }, min: -1, max: 1 },
                        y: { grid: { display: false }, ticks: { font: { size: 10 } } },
                    },
                    plugins: { legend: { display: false } },
                },
            });
        } catch {}
    }

    async function loadReportSummary() {
        const el = App.$("home-report-summary");
        if (!el) return;

        try {
            const data = await App.api("/api/predictions/latest");
            const preds = data.predictions || {};
            const counts = {};
            Object.values(preds).forEach(p => {
                const action = p.action || "HOLD";
                counts[action] = (counts[action] || 0) + 1;
            });

            const order = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"];
            let html = "";
            order.forEach(action => {
                if (!counts[action]) return;
                const color = App.actionColor(action);
                html += `<span class="home-action-chip" style="background:${color}22;color:${color};border:1px solid ${color}44">${counts[action]} ${action}</span> `;
            });
            el.innerHTML = html || '<span class="text-muted">No predictions yet</span>';
        } catch {}
    }

    async function loadCatalystSummary() {
        const el = App.$("home-catalyst-summary");
        if (!el) return;

        try {
            const data = await App.api("/api/catalyst/alerts?hours=24");
            const alerts = data.alerts || [];
            const directAlert = alerts.find(a => a.event_type === "direct_mention");
            const picks = directAlert ? directAlert.picks : [];

            if (picks.length === 0) {
                el.innerHTML = '<span class="text-muted">No active catalyst alerts</span>';
                return;
            }

            let html = "";
            picks.slice(0, 5).forEach(p => {
                const icon = p.direction === "bullish" ? "^" : "v";
                const cls = p.direction === "bullish" ? "text-green" : "text-red";
                html += `<div class="home-catalyst-row">
                    <span class="${cls}">${icon}</span>
                    <strong>${App.esc(p.symbol)}</strong>
                    <span class="text-muted">${App.esc((p.name || "").substring(0, 20))}</span>
                    <span class="${cls}">${(p.predicted_move_pct > 0 ? "+" : "")}${(p.predicted_move_pct || 0).toFixed(1)}%</span>
                </div>`;
            });
            el.innerHTML = html;
        } catch {}
    }

    // ── Sectors Section (full — delegates to existing sectors code) ─────

    function loadSectorsFull() {
        if (App.tabs.sectors && App.tabs.sectors.load) {
            App.tabs.sectors.load();
        }
    }

    // ── Report Section (delegates to existing report code) ─────────────

    function loadReport() {
        if (App.tabs.report && App.tabs.report.load) {
            App.tabs.report.load();
        }
    }

    function runBatch() {
        if (App.tabs.report && App.tabs.report.runBatch) {
            App.tabs.report.runBatch();
        }
    }

    // ── Trends Section (delegates to existing trends code) ─────────────

    function loadTrend() {
        if (App.tabs.trends) App.tabs.trends.loadTrend();
    }

    function loadHistory() {
        if (App.tabs.trends) App.tabs.trends.loadHistory();
    }

    function loadSectorHistory() {
        if (App.tabs.trends) App.tabs.trends.loadSectorHistory();
    }

    function goAnalyze() {
        const symbol = App.$("trend-symbol-input")?.value?.trim();
        // Switch to Stocks tab
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
        document.querySelector('[data-tab="stocks-tab"]')?.classList.add("active");
        App.$("stocks-tab")?.classList.add("active");
        document.querySelectorAll(".tab").forEach(t => t.setAttribute("aria-selected", t.classList.contains("active")));
        // Pre-fill and analyze
        if (App.$("symbol-input")) App.$("symbol-input").value = symbol;
        if (symbol && symbol.endsWith(".KL")) App.tabs.stocks?.switchMarket("MY");
        else App.tabs.stocks?.switchMarket("US");
        App.tabs.stocks?.analyze();
    }

    function quickTrend(symbol) {
        if (App.tabs.trends) App.tabs.trends.quickTrend(symbol);
    }

    // ── Sub-section Navigation ──────────────────────────────────────────

    function switchSection(section) {
        _activeSection = section;

        // Toggle visibility
        document.querySelectorAll(".home-section").forEach(el => el.classList.add("hidden"));
        const target = App.$("home-section-" + section);
        if (target) target.classList.remove("hidden");

        // Update active button
        document.querySelectorAll(".home-sub-tab").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.section === section);
        });

        // Lazy-load section content
        if (section === "overview") loadOverview();
        else if (section === "sectors") loadSectorsFull();
        else if (section === "report") loadReport();
        else if (section === "trends") loadHistory();
    }

    // ── Tab Activation ──────────────────────────────────────────────────

    function activate() {
        if (!_initialized) {
            _initialized = true;
            // Set up sub-tab click handlers
            document.querySelectorAll(".home-sub-tab").forEach(btn => {
                btn.addEventListener("click", () => switchSection(btn.dataset.section));
            });
        }
        switchSection(_activeSection);
    }

    // Register
    App.tabs.home = {
        activate,
        switchSection,
        loadSectorsFull,
        loadReport, runBatch,
        loadTrend, loadHistory, loadSectorHistory, goAnalyze, quickTrend,
    };
})();
