/**
 * Catalyst Alerts Tab — news-driven stock picks for next 24h.
 *
 * Shows: detected catalyst events, ranked stock picks, scan history.
 * Auto-refreshes every 30 minutes.
 */
(function () {
    "use strict";

    const AUTO_REFRESH_MS = 30 * 60 * 1000; // 30 min
    let refreshTimer = null;

    // ── Load alerts from DB ─────────────────────────────────────────────
    async function loadAlerts() {
        const eventsEl = document.getElementById("catalyst-events-list");
        const picksEl = document.getElementById("catalyst-picks-list");
        const directUsEl = document.getElementById("catalyst-direct-us-list");
        const directMyEl = document.getElementById("catalyst-direct-my-list");
        const histEl = document.getElementById("catalyst-history-list");
        const scanTimeEl = document.getElementById("catalyst-last-scan");

        try {
            const [alertsRes, histRes] = await Promise.all([
                App.api("/api/catalyst/alerts?hours=24"),
                App.api("/api/catalyst/history?days=7"),
            ]);

            const alerts = alertsRes.alerts || [];
            const directAlert = alerts.find(a => a.event_type === "direct_mention");
            const industryAlerts = alerts.filter(a => a.event_type !== "direct_mention");
            const allDirect = directAlert ? directAlert.picks : [];

            const usPicks = allDirect.filter(p => !p.symbol.endsWith(".KL"));
            const myPicks = allDirect.filter(p => p.symbol.endsWith(".KL"));

            renderEvents(eventsEl, industryAlerts);
            if (directUsEl) renderPicksDirect(directUsEl, usPicks);
            if (directMyEl) renderPicksDirect(directMyEl, myPicks);
            renderPicks(picksEl, alerts);
            renderHistory(histEl, histRes.history || []);

            if (alertsRes.alerts && alertsRes.alerts.length > 0) {
                const latest = alertsRes.alerts[0];
                scanTimeEl.textContent = "Last scan: " + formatTime(latest.scanned_at);
            } else {
                scanTimeEl.textContent = "No recent scans";
            }
        } catch (e) {
            eventsEl.innerHTML = '<p class="text-muted">No catalyst data yet. Click "Scan Now" to run first scan.</p>';
            picksEl.innerHTML = "";
        }
    }

    // ── Trigger manual scan ─────────────────────────────────────────────
    async function triggerScan() {
        const eventsEl = document.getElementById("catalyst-events-list");
        const picksEl = document.getElementById("catalyst-picks-list");
        const directUsEl = document.getElementById("catalyst-direct-us-list");
        const directMyEl = document.getElementById("catalyst-direct-my-list");
        const scanTimeEl = document.getElementById("catalyst-last-scan");

        eventsEl.innerHTML = '<div class="skeleton-line"></div><div class="skeleton-line"></div>';
        picksEl.innerHTML = '<div class="skeleton-line"></div><div class="skeleton-line"></div>';
        if (directUsEl) directUsEl.innerHTML = '<div class="skeleton-line"></div>';
        if (directMyEl) directMyEl.innerHTML = '<div class="skeleton-line"></div>';
        scanTimeEl.textContent = "Scanning...";

        try {
            const res = await App.api("/api/catalyst/scan", { method: "POST" });
            const allDirect = res.direct_picks || [];
            const usPicks = allDirect.filter(p => !p.symbol.endsWith(".KL"));
            const myPicks = allDirect.filter(p => p.symbol.endsWith(".KL"));

            renderEvents(eventsEl, wrapEvents(res));
            renderPicksDirect(picksEl, res.picks || []);
            if (directUsEl) renderPicksDirect(directUsEl, usPicks);
            if (directMyEl) renderPicksDirect(directMyEl, myPicks);
            scanTimeEl.textContent = "Scanned: " + formatTime(res.scanned_at);

            const directCount = (res.direct_picks || []).length;
            const eventCount = (res.events || []).length;
            App.toast(
                directCount + " stock mentions, " + eventCount + " events, " +
                (res.picks || []).length + " total picks",
                "success"
            );
        } catch (e) {
            eventsEl.innerHTML = '<p class="text-error">Scan failed: ' + App.esc(e.message) + "</p>";
            scanTimeEl.textContent = "Scan failed";
        }
    }

    // ── Render helpers ──────────────────────────────────────────────────

    function wrapEvents(scanRes) {
        // Convert scan response events into alert-like objects
        return (scanRes.events || []).map(e => ({
            event_type: e.event_type,
            event_label: e.label,
            headline: e.headline,
            sentiment: e.sentiment,
            confidence: e.confidence,
            affected_industries: e.affected_industries,
            picks: (scanRes.picks || []).filter(p => p.catalyst_type === e.event_type),
            scanned_at: scanRes.scanned_at,
        }));
    }

    function renderEvents(el, alerts) {
        if (!alerts || alerts.length === 0) {
            el.innerHTML = '<p class="text-muted">No catalyst events detected in recent news.</p>';
            return;
        }

        let html = "";
        for (const a of alerts) {
            const confPct = Math.round((a.confidence || 0) * 100);
            const sentIcon = (a.sentiment || 0) > 0 ? "+" : (a.sentiment || 0) < 0 ? "-" : "~";
            const sentClass = (a.sentiment || 0) > 0 ? "text-green" : (a.sentiment || 0) < 0 ? "text-red" : "text-muted";

            let industries = "";
            const affected = a.affected_industries || {};
            for (const [ind, dir] of Object.entries(affected)) {
                const dirIcon = dir === "bullish" ? "^" : "v";
                const dirClass = dir === "bullish" ? "text-green" : "text-red";
                industries += '<span class="catalyst-ind ' + dirClass + '">' + dirIcon + " " + App.esc(ind) + "</span> ";
            }

            html += '<div class="catalyst-event-card">' +
                '<div class="catalyst-event-header">' +
                    '<span class="catalyst-badge">' + App.esc(a.event_label || a.event_type) + "</span>" +
                    '<span class="catalyst-conf">' + confPct + "% conf</span>" +
                "</div>" +
                '<p class="catalyst-headline">' + App.esc(a.headline || "") + "</p>" +
                '<div class="catalyst-industries">' + industries + "</div>" +
            "</div>";
        }
        el.innerHTML = html;
    }

    function renderPicks(el, alerts) {
        // Collect all picks from all alerts
        const allPicks = [];
        for (const a of alerts) {
            for (const p of (a.picks || [])) {
                allPicks.push(p);
            }
        }
        // Dedupe by symbol, keep highest score
        const seen = {};
        for (const p of allPicks) {
            if (!seen[p.symbol] || p.score > seen[p.symbol].score) {
                seen[p.symbol] = p;
            }
        }
        const picks = Object.values(seen).sort((a, b) => b.score - a.score).slice(0, 10);
        renderPicksDirect(el, picks);
    }

    function renderPicksDirect(el, picks) {
        if (!picks || picks.length === 0) {
            el.innerHTML = '<p class="text-muted">No stock picks from current events.</p>';
            return;
        }

        let html = '<table class="catalyst-table"><thead><tr>' +
            "<th>#</th><th>Symbol</th><th>Name</th><th>Direction</th>" +
            "<th>Score</th><th>Est. Move</th><th>Price</th><th>Reason</th>" +
            "</tr></thead><tbody>";

        for (let i = 0; i < picks.length; i++) {
            const p = picks[i];
            const dirClass = p.direction === "bullish" ? "text-green" : "text-red";
            const dirIcon = p.direction === "bullish" ? "^" : "v";
            const moveStr = (p.predicted_move_pct > 0 ? "+" : "") + (p.predicted_move_pct || 0).toFixed(1) + "%";
            const reason = (p.reasons || []).join("; ");

            html += "<tr>" +
                "<td>" + (i + 1) + "</td>" +
                '<td><strong>' + App.esc(p.symbol) + "</strong></td>" +
                "<td>" + App.esc((p.name || "").substring(0, 25)) + "</td>" +
                '<td class="' + dirClass + '">' + dirIcon + " " + App.esc(p.direction) + "</td>" +
                "<td>" + (p.score || 0).toFixed(0) + "</td>" +
                '<td class="' + dirClass + '">' + moveStr + "</td>" +
                "<td>$" + (p.current_price || 0).toFixed(2) + "</td>" +
                '<td class="text-muted" style="font-size:0.8rem;max-width:250px;">' + App.esc(reason) + "</td>" +
                "</tr>";
        }

        html += "</tbody></table>";
        el.innerHTML = html;
    }

    function renderHistory(el, history) {
        if (!history || history.length === 0) {
            el.innerHTML = '<p class="text-muted">No scan history yet.</p>';
            return;
        }

        let html = '<table class="catalyst-table"><thead><tr>' +
            "<th>Time</th><th>Event</th><th>Confidence</th><th>Headline</th>" +
            "</tr></thead><tbody>";

        for (const h of history.slice(0, 20)) {
            const confPct = Math.round((h.confidence || 0) * 100);
            html += "<tr>" +
                "<td>" + formatTime(h.scanned_at) + "</td>" +
                "<td>" + App.esc(h.event_label || h.event_type) + "</td>" +
                "<td>" + confPct + "%</td>" +
                '<td class="text-muted" style="max-width:300px;">' + App.esc((h.headline || "").substring(0, 80)) + "</td>" +
                "</tr>";
        }

        html += "</tbody></table>";
        el.innerHTML = html;
    }

    function formatTime(iso) {
        if (!iso) return "—";
        try {
            const d = new Date(iso);
            return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
        } catch (e) {
            return iso;
        }
    }

    // ── Tab activation / auto-refresh ───────────────────────────────────

    function onTabActivate() {
        loadAlerts();
        if (!refreshTimer) {
            refreshTimer = setInterval(loadAlerts, AUTO_REFRESH_MS);
        }
    }

    function onTabDeactivate() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
    }

    // Register with App
    if (window.App) {
        App.tabs = App.tabs || {};
        App.tabs["catalyst-tab"] = { activate: onTabActivate, deactivate: onTabDeactivate };
        App.actions = App.actions || {};
        App.actions["catalyst-scan"] = triggerScan;
    }
})();
