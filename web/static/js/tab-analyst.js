/**
 * AI Analyst Tab — self-learning stock picks with LLM reasoning.
 *
 * Shows: today's picks, scorecard (Option B: date chips + run buttons),
 * performance review (Option C: heatmap), weekend banner, mode toggle.
 */
(function () {
    "use strict";

    // ── State ──────────────────────────────────────────────────────────
    var _evaluatedReports = [];   // full list from /api/analyst/evaluated-reports
    var _byDate = {};             // { "2026-04-14": [report, ...], ... }

    // ── Weekend / context banner ───────────────────────────────────────
    function getWeekendContext() {
        var now = new Date();
        var dow  = now.getDay();   // 0=Sun 1=Mon … 6=Sat
        var hour = now.getHours();

        if (dow >= 1 && dow <= 5) return null; // weekday — no banner

        if (dow === 6) { // Saturday
            if (hour < 18) {
                return {
                    type: "info",
                    msg: "Markets are closed. Scorecard evaluation works normally — new picks will target Monday's open.",
                };
            }
            return {
                type: "warning",
                msg: "Saturday evening — picks generated now will be 2 days stale by Monday open. Consider waiting until Sunday evening or Monday morning.",
            };
        }

        if (dow === 0) { // Sunday
            if (hour >= 18) {
                return {
                    type: "info",
                    msg: "Sunday evening — running as Monday prep. Picks will be evaluated against Monday's close (~24 h).",
                };
            }
            return {
                type: "warning",
                msg: "Markets are closed until Monday. Evaluation still works. For new picks, consider waiting until Sunday evening.",
            };
        }

        return null;
    }

    function renderWeekendBanner() {
        var el = document.getElementById("analyst-weekend-banner");
        if (!el) return;
        var ctx = getWeekendContext();
        if (!ctx) { el.style.display = "none"; return; }
        var bg    = ctx.type === "warning" ? "rgba(255,171,0,0.12)" : "rgba(33,150,243,0.1)";
        var border = ctx.type === "warning" ? "#ffab00" : "#2196f3";
        var icon   = ctx.type === "warning" ? "⚠️" : "ℹ️";
        el.style.cssText = "display:block;margin-bottom:0.75rem;padding:0.6rem 1rem;" +
            "border-radius:8px;font-size:0.85rem;background:" + bg + ";" +
            "border-left:3px solid " + border + ";color:#e4e6ef;";
        el.textContent = icon + "  " + ctx.msg;
    }

    // ── Mode toggle ────────────────────────────────────────────────────
    function getMode() {
        var active = document.querySelector(".analyst-mode-btn.active");
        return active ? active.dataset.mode : "both";
    }

    document.querySelectorAll(".analyst-mode-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".analyst-mode-btn").forEach(function (b) {
                b.style.background = "transparent";
                b.style.color = "#9ea3b0";
                b.classList.remove("active");
            });
            this.style.background = "#3a3f5c";
            this.style.color = "#e4e6ef";
            this.classList.add("active");
        });
    });

    // ── Load latest picks ──────────────────────────────────────────────
    async function loadLatest() {
        var picksEl   = document.getElementById("analyst-picks-list");
        var summaryEl = document.getElementById("analyst-summary-text");
        var lastRunEl = document.getElementById("analyst-last-run");
        var market    = document.getElementById("analyst-market-filter").value || undefined;
        var qs        = market ? "?market=" + market : "";

        try {
            var res    = await App.api("/api/analyst/latest" + qs);
            var report = res.report;
            if (report) {
                renderPicks(picksEl, report.picks || []);
                summaryEl.textContent = report.summary || "No summary available.";
                lastRunEl.textContent = "Last run: " + formatTime(report.created_at);
                document.getElementById("analyst-stat-headlines").textContent = report.headlines_used || 0;
                updateNewsRange("analyst-news-range", report.created_at, 6);
            } else {
                picksEl.innerHTML = '<p class="text-muted">No analysis available yet. Click "Run" to start.</p>';
                summaryEl.textContent = "No analysis available yet.";
                lastRunEl.textContent = "";
                document.getElementById("analyst-news-range").textContent = "";
            }
        } catch (e) {
            picksEl.innerHTML = '<p class="text-muted">Failed to load analyst data.</p>';
        }
    }

    // ── Option B: Scorecard chip selector ─────────────────────────────
    async function loadScorecardSelector() {
        var chipsEl = document.getElementById("analyst-date-chips");
        var btnsEl  = document.getElementById("analyst-run-btns");
        var scoreEl = document.getElementById("analyst-scorecard-list");
        var market  = document.getElementById("analyst-market-filter").value || undefined;
        var qs      = market ? "?market=" + market : "";

        try {
            var res = await App.api("/api/analyst/evaluated-reports" + qs);
            _evaluatedReports = res.reports || [];

            if (_evaluatedReports.length === 0) {
                chipsEl.innerHTML = '<span class="text-muted" style="font-size:0.85rem;">No evaluated runs yet — first outcomes appear ~24h after the first analyst run.</span>';
                btnsEl.innerHTML  = "";
                scoreEl.innerHTML = '<p class="text-muted">No evaluated picks yet.</p>';
                document.getElementById("analyst-scorecard-meta").textContent = "";
                return;
            }

            // Group by local date
            _byDate = {};
            _evaluatedReports.forEach(function (r) {
                var d = toLocalDateKey(r.created_at);
                if (!_byDate[d]) _byDate[d] = [];
                _byDate[d].push(r);
            });

            var dates = Object.keys(_byDate).sort().reverse();

            // Render date chips
            chipsEl.innerHTML = dates.map(function (d, i) {
                return '<button class="analyst-chip' + (i === 0 ? " active" : "") + '" ' +
                    'data-date="' + App.esc(d) + '" ' +
                    'style="white-space:nowrap;padding:0.25rem 0.7rem;border:1px solid ' +
                    (i === 0 ? "#5c6bc0" : "#2e3148") + ';border-radius:20px;cursor:pointer;font-size:0.8rem;' +
                    'background:' + (i === 0 ? "#3a3f5c" : "#1e2235") + ';color:' +
                    (i === 0 ? "#e4e6ef" : "#9ea3b0") + ';flex-shrink:0;">' +
                    App.esc(formatDateChip(d)) + "</button>";
            }).join("");

            // Chip click handler
            chipsEl.querySelectorAll(".analyst-chip").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    chipsEl.querySelectorAll(".analyst-chip").forEach(function (b) {
                        b.style.background = "#1e2235"; b.style.color = "#9ea3b0";
                        b.style.borderColor = "#2e3148"; b.classList.remove("active");
                    });
                    this.style.background = "#3a3f5c"; this.style.color = "#e4e6ef";
                    this.style.borderColor = "#5c6bc0"; this.classList.add("active");
                    renderRunBtns(_byDate[this.dataset.date] || []);
                });
            });

            renderRunBtns(_byDate[dates[0]] || []);

        } catch (e) {
            chipsEl.innerHTML = '<span class="text-muted">Failed to load scorecard history.</span>';
        }
    }

    function renderRunBtns(runs) {
        var btnsEl = document.getElementById("analyst-run-btns");
        if (!runs.length) { btnsEl.innerHTML = ""; return; }

        var sorted = runs.slice().sort(function (a, b) {
            return a.created_at.localeCompare(b.created_at);
        });

        btnsEl.innerHTML = sorted.map(function (r, i) {
            var pct   = r.picks_count ? Math.round((r.correct_count / r.picks_count) * 100) : 0;
            var color = pct >= 60 ? "#00c853" : pct >= 40 ? "#ffab00" : "#f44336";
            var time  = formatTimeOnly(r.created_at);
            var label = capitalize(r.run_type || "run");
            var isFirst = i === 0;
            return '<button class="analyst-run-btn' + (isFirst ? " active" : "") + '" ' +
                'data-report="' + App.esc(r.report_id) + '" ' +
                'style="display:flex;flex-direction:column;align-items:flex-start;gap:2px;' +
                'padding:0.4rem 0.8rem;border:1px solid ' + (isFirst ? "#5c6bc0" : "#2e3148") + ';' +
                'border-radius:8px;cursor:pointer;background:' + (isFirst ? "#252d4a" : "#1e2235") + ';' +
                'min-width:90px;">' +
                '<span style="font-weight:600;font-size:0.85rem;color:#e4e6ef;">' + App.esc(label) + "</span>" +
                '<span style="font-size:0.72rem;color:#9ea3b0;">' + App.esc(time) + "</span>" +
                '<span style="font-size:0.78rem;font-weight:600;color:' + color + ';">' +
                r.correct_count + "/" + r.picks_count + " · " + pct + "%" +
                "</span></button>";
        }).join("");

        // Wire click handlers
        btnsEl.querySelectorAll(".analyst-run-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                btnsEl.querySelectorAll(".analyst-run-btn").forEach(function (b) {
                    b.style.background = "#1e2235"; b.style.borderColor = "#2e3148";
                    b.classList.remove("active");
                });
                this.style.background = "#252d4a"; this.style.borderColor = "#5c6bc0";
                this.classList.add("active");
                loadScorecardForReport(this.dataset.report);
            });
        });

        // Auto-load first
        loadScorecardForReport(sorted[0].report_id);
    }

    async function loadScorecardForReport(reportId) {
        if (!reportId) return;
        var scoreEl    = document.getElementById("analyst-scorecard-list");
        var scoreMetaEl = document.getElementById("analyst-scorecard-meta");

        try {
            var res = await App.api("/api/analyst/report/" + encodeURIComponent(reportId));
            var report   = res.report;
            var outcomes = res.outcomes || [];

            // Try to fetch attribution alongside (optional — not all reports have archived briefings)
            var attributionMap = {};
            try {
                var attr = await App.api("/api/analyst/attribution/" + encodeURIComponent(reportId));
                if (attr && attr.attributions) {
                    attr.attributions.forEach(function (a) {
                        if (a && a.symbol) attributionMap[a.symbol] = a;
                    });
                }
            } catch (e) { /* no briefing archived — fine */ }

            if (report && scoreMetaEl) {
                var correct = outcomes.filter(function (o) { return o.is_correct === 1; }).length;
                var total   = outcomes.length;
                var pct     = total ? Math.round((correct / total) * 100) : 0;
                scoreMetaEl.textContent = "— " + capitalize(report.run_type || "run") +
                    " @ " + formatTime(report.created_at) +
                    " · " + correct + "/" + total + " correct (" + pct + "%)";
            }
            renderScorecard(scoreEl, outcomes, attributionMap);
        } catch (e) {
            renderScorecard(scoreEl, []);
            if (scoreMetaEl) scoreMetaEl.textContent = "";
        }
    }

    // Sync chip + run-btn selection when heatmap dot is clicked
    function syncChipsToReport(reportId) {
        var report = _evaluatedReports.find(function (r) { return r.report_id === reportId; });
        if (!report) return;
        var dateKey = toLocalDateKey(report.created_at);

        // Activate the right chip
        var chipsEl = document.getElementById("analyst-date-chips");
        chipsEl.querySelectorAll(".analyst-chip").forEach(function (btn) {
            var isMatch = btn.dataset.date === dateKey;
            btn.style.background   = isMatch ? "#3a3f5c" : "#1e2235";
            btn.style.color        = isMatch ? "#e4e6ef" : "#9ea3b0";
            btn.style.borderColor  = isMatch ? "#5c6bc0" : "#2e3148";
            if (isMatch) btn.classList.add("active"); else btn.classList.remove("active");
        });

        // Re-render run buttons for that date with the right one pre-selected
        var runs = _byDate[dateKey] || [];
        renderRunBtns(runs);

        // Override active run btn to the correct one
        var btnsEl = document.getElementById("analyst-run-btns");
        btnsEl.querySelectorAll(".analyst-run-btn").forEach(function (btn) {
            var isMatch = btn.dataset.report === reportId;
            btn.style.background  = isMatch ? "#252d4a" : "#1e2235";
            btn.style.borderColor = isMatch ? "#5c6bc0" : "#2e3148";
            if (isMatch) btn.classList.add("active"); else btn.classList.remove("active");
        });
    }

    // ── Option C: Performance Review heatmap ──────────────────────────
    function renderHeatmap(reports) {
        var el = document.getElementById("analyst-heatmap");
        if (!reports || !reports.length) {
            el.innerHTML = '<p class="text-muted">No evaluated runs yet.</p>';
            return;
        }

        // Group by local date
        var byDate = {};
        reports.forEach(function (r) {
            var d    = toLocalDateKey(r.created_at);
            var slot = normalizeSlot(r.run_type);
            if (!byDate[d]) byDate[d] = {};
            // keep earliest if duplicate slot (shouldn't happen)
            if (!byDate[d][slot]) byDate[d][slot] = r;
            // also store "other" runs under run_type directly for manual runs
            byDate[d]["__" + r.report_id] = r; // keep full list for day-bar calc
        });

        var dates = Object.keys(byDate).filter(function (k) { return !k.startsWith("__"); })
                          .sort().reverse();

        var slots      = ["morning", "midday", "evening"];
        var slotLabels = { morning: "Morning", midday: "Midday", evening: "Evening" };

        var html = '<div style="overflow-x:auto;">' +
            '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">' +
            '<thead><tr>' +
            '<th style="text-align:left;padding:0.4rem 0.6rem;color:#9ea3b0;font-weight:500;">Date</th>' +
            '<th style="text-align:left;padding:0.4rem 0.6rem;color:#9ea3b0;font-weight:500;">Day</th>';
        slots.forEach(function (s) {
            html += '<th style="text-align:center;padding:0.4rem 0.6rem;color:#9ea3b0;font-weight:500;">' +
                slotLabels[s] + "</th>";
        });
        html += "</tr></thead><tbody>";

        dates.forEach(function (date) {
            var dayRuns = byDate[date];
            // Day accuracy = sum across morning/midday/evening
            var dayTotal = 0, dayCorrect = 0;
            slots.forEach(function (s) {
                if (dayRuns[s]) {
                    dayTotal   += (dayRuns[s].picks_count  || 0);
                    dayCorrect += (dayRuns[s].correct_count || 0);
                }
            });
            var dayPct    = dayTotal ? Math.round(dayCorrect / dayTotal * 100) : null;
            var barColor  = dayPct === null ? "#555" :
                            dayPct >= 60    ? "#00c853" :
                            dayPct >= 40    ? "#ffab00" : "#f44336";
            var dayLabel  = formatDateLabel(date);

            html += '<tr style="border-top:1px solid #2e3148;">';
            html += '<td style="padding:0.5rem 0.6rem;white-space:nowrap;">' + App.esc(dayLabel) + "</td>";
            html += "<td style=\"padding:0.5rem 0.6rem;\">";
            if (dayPct !== null) {
                html += '<div style="display:flex;align-items:center;gap:0.4rem;">' +
                    '<div style="height:5px;width:' + Math.max(4, Math.round(dayPct * 0.5)) + 'px;' +
                    'background:' + barColor + ';border-radius:3px;transition:width 0.3s;"></div>' +
                    '<span style="color:' + barColor + ';font-weight:600;">' + dayPct + '%</span></div>';
            } else {
                html += '<span style="color:#555;">—</span>';
            }
            html += "</td>";

            slots.forEach(function (s) {
                var r = dayRuns[s];
                html += '<td style="text-align:center;padding:0.5rem 0.6rem;">';
                if (!r) {
                    html += '<span style="color:#555;">—</span>';
                } else {
                    var pct   = r.picks_count ? Math.round(r.correct_count / r.picks_count * 100) : 0;
                    var color = pct >= 60 ? "#00c853" : pct >= 40 ? "#ffab00" : "#f44336";
                    var title = r.correct_count + "/" + r.picks_count + " correct";
                    html += '<button class="perf-dot" data-report="' + App.esc(r.report_id) + '" ' +
                        'title="' + App.esc(title) + '" ' +
                        'style="width:36px;height:36px;border-radius:50%;border:2px solid ' + color + ';' +
                        'background:transparent;cursor:pointer;color:' + color + ';' +
                        'font-size:0.68rem;font-weight:700;line-height:1;' +
                        'display:flex;align-items:center;justify-content:center;padding:0;' +
                        'transition:background 0.15s;">' +
                        pct + "%</button>";
                }
                html += "</td>";
            });
            html += "</tr>";
        });

        html += "</tbody></table></div>";
        el.innerHTML = '<div class="table-scroll">' + html + "</div>";

        // Dot hover effect + click → load scorecard
        el.querySelectorAll(".perf-dot").forEach(function (dot) {
            dot.addEventListener("mouseenter", function () {
                this.style.background = "rgba(255,255,255,0.08)";
            });
            dot.addEventListener("mouseleave", function () {
                this.style.background = "transparent";
            });
            dot.addEventListener("click", function () {
                var reportId = this.dataset.report;
                syncChipsToReport(reportId);
                loadScorecardForReport(reportId);
                // Scroll to scorecard card
                var scoreCard = document.getElementById("analyst-scorecard-list");
                if (scoreCard) scoreCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
            });
        });
    }

    // ── Load accuracy stats (summary row) ─────────────────────────────
    async function loadAccuracy() {
        try {
            var stats = await App.api("/api/analyst/accuracy?days=30");
            document.getElementById("analyst-stat-total").textContent    = stats.total   || 0;
            document.getElementById("analyst-stat-correct").textContent  = stats.correct || 0;
            document.getElementById("analyst-stat-accuracy").textContent =
                stats.accuracy_pct != null ? stats.accuracy_pct + "%" : "--";
        } catch (e) { /* silent */ }
        renderBucketedAccuracy();
    }

    function _cellColor(pct) {
        if (pct == null) return "var(--text-muted,#6b7280)";
        if (pct >= 55) return "#22c55e";
        if (pct >= 45) return "#eab308";
        return "#ef4444";
    }

    async function renderBucketedAccuracy() {
        var el = document.getElementById("analyst-bucketed-accuracy");
        if (!el) return;
        try {
            var d = await App.api("/api/analyst/accuracy-bucketed?days=90");
            var html = '<table class="data-table" style="width:100%;font-size:0.85rem;">'
                + '<thead><tr>'
                + '<th>Confidence</th>'
                + '<th style="text-align:right;">Bullish</th>'
                + '<th style="text-align:right;">Bearish</th>'
                + '<th style="text-align:right;">Total</th>'
                + '</tr></thead><tbody>';
            d.buckets.forEach(function (b) {
                var m = d.matrix[b];
                function cell(o) {
                    if (!o.n) return '<td style="text-align:right;color:var(--text-muted,#6b7280);">—</td>';
                    var color = _cellColor(o.pct);
                    return '<td style="text-align:right;"><span style="color:' + color + ';font-weight:600;">'
                        + o.pct + '%</span> '
                        + '<span style="color:var(--text-muted,#6b7280);font-size:0.75rem;">('
                        + o.correct + '/' + o.n + ')</span></td>';
                }
                html += '<tr>'
                    + '<td><code>' + App.esc(b) + '</code></td>'
                    + cell(m.bullish)
                    + cell(m.bearish)
                    + cell(m.total)
                    + '</tr>';
            });
            html += '</tbody></table>'
                + '<div class="text-muted" style="font-size:0.75rem;margin-top:0.35rem;">'
                + 'Green ≥55% · yellow 45-55% · red &lt;45%. Last 90 days. Picks capped to 0.65 when no concrete catalyst cited — so the 0.70+ bucket will thin over time.'
                + '</div>';
            el.innerHTML = html;
        } catch (e) {
            el.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">Bucketed accuracy unavailable</p>';
        }
    }

    // ── Trigger run (respects mode toggle) ────────────────────────────
    var ANALYST_STEPS = [
        { id: "news",       label: "Fetching News",        duration: 2000  },
        { id: "extract",    label: "Detecting Stocks",     duration: 3000  },
        { id: "technicals", label: "Technical Indicators", duration: 8000  },
        { id: "llm",        label: "LLM Analysis",         duration: 15000 },
        { id: "knowledge",  label: "Knowledge Graph",      duration: 3000  },
        { id: "scoring",    label: "Scoring & Ranking",    duration: 2000  },
    ];

    async function triggerRun() {
        var mode   = getMode();
        var market = document.getElementById("analyst-market-filter").value || "MY";

        // ── Eval-only ──
        if (mode === "eval") {
            var scoreEl = document.getElementById("analyst-scorecard-list");
            scoreEl.innerHTML = '<p class="text-muted">Running evaluation…</p>';
            try {
                var evalRes = await App.api("/api/analyst/run-eval", { method: "POST" });
                var n = evalRes.picks || 0;
                App.toast(n + " pick" + (n !== 1 ? "s" : "") + " evaluated", "success");
                await loadScorecardSelector();
                renderHeatmap(_evaluatedReports);
                loadAccuracy();
            } catch (e) {
                scoreEl.innerHTML = '<p class="text-error">Evaluation failed: ' + App.esc(e.message || "unknown") + "</p>";
            }
            return;
        }

        // ── Picks-only or Picks+Eval ──
        var picksEl   = document.getElementById("analyst-picks-list");
        var lastRunEl = document.getElementById("analyst-last-run");
        var summaryEl = document.getElementById("analyst-summary-text");

        picksEl.innerHTML = "";
        lastRunEl.textContent = "Running analysis…";
        summaryEl.textContent = "";
        App.progress.show("analyst-progress", ANALYST_STEPS, "Starting analysis…");

        // Fire eval first if "both" (it's fast, ~30s)
        if (mode === "both") {
            try {
                await App.api("/api/analyst/run-eval", { method: "POST" });
            } catch (e) { /* non-blocking */ }
        }

        try {
            var controller = new AbortController();
            var timeout = setTimeout(function () { controller.abort(); }, 10 * 60 * 1000);
            var res = await App.api("/api/analyst/run?market=" + market, {
                method: "POST",
                signal: controller.signal,
            });
            clearTimeout(timeout);

            App.progress.done("analyst-progress");
            renderPicks(picksEl, res.picks || []);
            summaryEl.textContent = res.summary || "Analysis complete.";
            lastRunEl.textContent = "Just now";
            document.getElementById("analyst-stat-headlines").textContent = res.headlines_used || 0;
            updateNewsRange("analyst-news-range", new Date().toISOString(), 6);
            App.toast((res.picks || []).length + " picks generated", "success");

            // Refresh scorecard + heatmap if eval was also run
            if (mode === "both") {
                await loadScorecardSelector();
                renderHeatmap(_evaluatedReports);
                loadAccuracy();
            }
        } catch (e) {
            App.progress.fail("analyst-progress", "Analysis failed");
            var errMsg = e.message || "Unknown error";
            if (e.name === "AbortError") {
                errMsg = "Request timed out (>10 min). The scheduled Claude tasks run without this limit.";
            } else if (errMsg.includes("503") || errMsg.includes("502")) {
                errMsg = "Server overloaded. The LLM analysis takes several minutes — please try again.";
            }
            picksEl.innerHTML = '<p class="text-error">Analysis failed: ' + App.esc(errMsg) + '</p>';
            lastRunEl.textContent = "Failed";
        }
    }

    // ── Render picks table ─────────────────────────────────────────────
    function renderPicks(el, picks) {
        if (!picks || picks.length === 0) {
            el.innerHTML = '<p class="text-muted">No picks in this report.</p>';
            return;
        }

        var html = '<table class="catalyst-table"><thead><tr>' +
            "<th>#</th><th>Symbol</th><th>Name</th><th>Direction</th>" +
            "<th>Score</th><th>Conf</th><th>Est. Move</th><th>Price</th>" +
            "</tr></thead><tbody>";

        for (var i = 0; i < picks.length; i++) {
            var p        = picks[i];
            var dirClass = p.direction === "bullish" ? "text-green" : "text-red";
            var dirIcon  = p.direction === "bullish" ? "^" : "v";
            var moveStr  = (p.predicted_move > 0 ? "+" : "") + (p.predicted_move || 0).toFixed(1) + "%";
            var confStr  = Math.round((p.confidence || 0) * 100) + "%";
            var priceStr = p.current_price ? "$" + p.current_price.toFixed(2) : "--";
            var isCascade = p.news_count === 0;

            html += "<tr>" +
                "<td>" + (i + 1) + "</td>" +
                '<td><strong>' + App.esc(p.symbol) + "</strong>" +
                (isCascade ? ' <span class="text-muted" style="font-size:0.7rem;">cascade</span>' : "") + "</td>" +
                "<td>" + App.esc((p.name || "").substring(0, 30)) + "</td>" +
                '<td class="' + dirClass + '">' + dirIcon + " " + App.esc(p.direction) + "</td>" +
                "<td>" + (p.score || 0).toFixed(0) + "</td>" +
                "<td>" + confStr + "</td>" +
                '<td class="' + dirClass + '">' + moveStr + "</td>" +
                "<td>" + priceStr + "</td></tr>";

            var bullItems = (p.bull_case  || []).filter(function (s) { return s; });
            var bearItems = (p.bear_case  || []).filter(function (s) { return s; });
            var reasons   = (p.reasoning || []).filter(function (s) { return s; });

            if (bullItems.length > 0 || reasons.length > 0) {
                html += '<tr class="analyst-detail-row" style="border-top:none;"><td></td>' +
                    '<td colspan="7" style="padding:0.2rem 0.5rem 0.5rem;font-size:0.8rem;">';
                if (reasons.length > 0) {
                    html += '<div style="margin-bottom:0.3rem;color:#e4e6ef;">' +
                        reasons.map(function (r) { return App.esc(r); }).join(" · ") + "</div>";
                }
                if (bullItems.length > 0 || bearItems.length > 0) {
                    html += '<div style="display:flex;gap:1.5rem;">';
                    if (bullItems.length > 0) {
                        html += '<div><span class="text-green" style="font-weight:600;">Bull:</span> ' +
                            bullItems.map(function (r) { return App.esc(r); }).join("; ") + "</div>";
                    }
                    if (bearItems.length > 0) {
                        html += '<div><span class="text-red" style="font-weight:600;">Bear:</span> ' +
                            bearItems.map(function (r) { return App.esc(r); }).join("; ") + "</div>";
                    }
                    html += "</div>";
                }
                html += "</td></tr>";
            }
        }
        html += "</tbody></table>";
        el.innerHTML = '<div class="table-scroll">' + html + "</div>";
    }

    // Pretty signal verdict pill
    function _signalPill(signalName, verdict, agreement) {
        var labels = { technical: "Tech", news: "News", fundamental: "Fund",
                       options: "Opt", "13f": "13F" };
        var label = labels[signalName] || signalName;
        var color = "#555";
        var title = signalName + ": " + (verdict || "n/a");
        if (agreement === "agree") {
            color = "#22c55e";
            title += " (agrees with Claude)";
        } else if (agreement === "disagree") {
            color = "#ef4444";
            title += " (disagrees with Claude)";
        } else if (verdict === "neutral") {
            color = "#94a3b8";
            title += " (neutral)";
        } else if (!verdict) {
            color = "#333";
            title = signalName + ": no data";
        }
        return '<span class="sc-signal-pill" style="background:' + color +
               '22;border:1px solid ' + color + ';color:' + color +
               ';" title="' + App.esc(title) + '">' + App.esc(label) + '</span>';
    }

    function _renderAttributionBlock(attr) {
        if (!attr || attr.error) return "";
        var pills = Object.keys(attr.verdicts || {}).map(function (s) {
            return _signalPill(s, attr.verdicts[s], attr.agreement[s]);
        }).join(" ");
        var summary = attr.agree_count + " agree · " + attr.disagree_count + " disagree";
        if (attr.signals_available != null)
            summary += " · " + attr.signals_available + "/5 signals available";
        return '<div style="margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid rgba(255,255,255,0.06);">' +
               '<div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.3rem;">' +
                 'Signal attribution <span style="color:#64748b;text-transform:none;letter-spacing:0;">· ' + summary + '</span>' +
               '</div>' +
               '<div class="sc-signal-pills">' + pills + '</div>' +
               '</div>';
    }

    // ── Render scorecard table ─────────────────────────────────────────
    function renderScorecard(el, outcomes, attributionMap) {
        if (!outcomes || outcomes.length === 0) {
            el.innerHTML = '<p class="text-muted">No evaluated picks yet.</p>';
            return;
        }
        attributionMap = attributionMap || {};

        var html = '<table class="catalyst-table"><thead><tr>' +
            "<th>Symbol</th><th>Name</th><th>Direction</th><th>Conf</th>" +
            "<th>Predicted</th><th>Actual</th><th>Result</th><th>Why wrong?</th>" +
            "</tr></thead><tbody>";

        outcomes.forEach(function (o, idx) {
            var predStr    = (o.predicted_move > 0 ? "+" : "") + (o.predicted_move || 0).toFixed(1) + "%";
            var actStr     = o.actual_move_24h != null
                ? (o.actual_move_24h > 0 ? "+" : "") + o.actual_move_24h.toFixed(2) + "%" : "--";
            var isCorrect  = o.is_correct === 1;
            var resultClass = isCorrect ? "text-green" : "text-red";
            var dirClass   = o.direction === "bullish" ? "text-green" : "text-red";
            var confStr    = Math.round((o.confidence || 0) * 100) + "%";
            var rowId      = "sc-detail-" + idx;

            // Intra-window extremes (only render if measured)
            var extremesStr = "";
            if (o.peak_favorable_move != null && o.max_adverse_move != null) {
                var peak = (o.peak_favorable_move > 0 ? "+" : "") + o.peak_favorable_move.toFixed(2) + "%";
                var adv  = (o.max_adverse_move > 0 ? "+" : "") + o.max_adverse_move.toFixed(2) + "%";
                extremesStr =
                    '<div style="font-size:0.7rem;color:#94a3b8;margin-top:0.15rem;">' +
                    '<span style="color:#22c55e;">peak ' + peak + '</span> / ' +
                    '<span style="color:#ef4444;">low ' + adv + '</span></div>';
            }
            // TIMING badge: directionally right but exit-timed wrong
            var timingBadge = "";
            if (!isCorrect && o.directional_hit === 1) {
                timingBadge =
                    '<span style="display:inline-block;margin-left:0.4rem;padding:0.05rem 0.35rem;' +
                    'font-size:0.65rem;background:rgba(245,158,11,0.18);color:#f59e0b;' +
                    'border:1px solid rgba(245,158,11,0.4);border-radius:0.25rem;font-weight:600;" ' +
                    'title="Direction was right at some point in the window — exit timing failed">TIMING</span>';
            }

            // Failure analysis cell
            var failureCell = '<td class="text-muted" style="font-size:0.78rem;">—</td>';
            if (!isCorrect && o.failure_analysis) {
                var fa = o.failure_analysis;
                var reason = App.esc(fa.primary_reason || "");
                var lesson = App.esc(fa.lesson || "");
                var over   = App.esc(fa.overweighted_signal || "");
                var under  = App.esc(fa.underweighted_signal || "");
                failureCell =
                    '<td style="font-size:0.78rem;max-width:220px;">' +
                    '<span style="color:#f59e0b;font-weight:600;">' + reason + '</span>' +
                    (over ? '<br><span class="text-muted">over: ' + over + '</span>' : '') +
                    (under ? ' · <span class="text-muted">under: ' + under + '</span>' : '') +
                    (lesson ? '<br><em style="color:#94a3b8;">' + lesson + '</em>' : '') +
                    '</td>';
            } else if (!isCorrect) {
                failureCell = '<td style="font-size:0.78rem;color:#555;font-style:italic;">pending analysis</td>';
            }

            // Main row — clicking expands reasoning
            html += '<tr class="sc-main-row" data-target="' + rowId + '" style="cursor:pointer;" title="Click to expand reasoning">' +
                '<td><strong>' + App.esc(o.symbol) + "</strong></td>" +
                "<td>" + App.esc((o.name || "").substring(0, 32)) + "</td>" +
                '<td class="' + dirClass + '">' + App.esc(o.direction) + "</td>" +
                "<td>" + confStr + "</td>" +
                "<td>" + predStr + "</td>" +
                "<td>" + actStr + extremesStr + "</td>" +
                '<td class="' + resultClass + '" style="font-weight:600;">' +
                (isCorrect ? "✓ Correct" : "✗ Wrong") + timingBadge + "</td>" +
                failureCell + "</tr>";

            // Expandable detail row
            var bull  = (o.bull_case  || []).map(function(b){ return App.esc(b); }).join(" · ");
            var bear  = (o.bear_case  || []).map(function(b){ return App.esc(b); }).join(" · ");
            var risks = (o.key_risks  || []).map(function(r){ return App.esc(r); }).join(" · ");
            var reasoning = App.esc(o.pick_reasoning || "");
            var catalyst  = App.esc(o.catalyst_headline || "");

            var attributionHtml = _renderAttributionBlock(attributionMap[o.symbol]);

            html += '<tr id="' + rowId + '" class="sc-detail-row" style="display:none;">' +
                '<td colspan="8" style="padding:0.75rem 1rem 1rem;background:rgba(255,255,255,0.03);border-top:1px solid rgba(255,255,255,0.06);">' +
                (catalyst ? '<div style="margin-bottom:0.4rem;font-size:0.8rem;color:#94a3b8;">📰 ' + catalyst + '</div>' : '') +
                (reasoning ? '<div style="margin-bottom:0.5rem;font-size:0.85rem;">' + reasoning + '</div>' : '') +
                (bull  ? '<div style="font-size:0.78rem;color:#22c55e;margin-bottom:0.2rem;"><strong>Bull:</strong> ' + bull  + '</div>' : '') +
                (bear  ? '<div style="font-size:0.78rem;color:#ef4444;margin-bottom:0.2rem;"><strong>Bear:</strong> ' + bear  + '</div>' : '') +
                (risks ? '<div style="font-size:0.78rem;color:#f59e0b;"><strong>Risks:</strong> ' + risks + '</div>' : '') +
                attributionHtml +
                '</td></tr>';
        });

        html += "</tbody></table>";
        el.innerHTML = '<div class="table-scroll">' + html + "</div>";

        // Toggle expand on row click
        el.querySelectorAll(".sc-main-row").forEach(function (row) {
            row.addEventListener("click", function () {
                var detail = document.getElementById(this.dataset.target);
                if (detail) {
                    var isOpen = detail.style.display !== "none";
                    detail.style.display = isOpen ? "none" : "table-row";
                }
            });
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────
    function toLocalDateKey(isoStr) {
        // isoStr is UTC from SQLite: "2026-04-14 09:22:53"
        // Convert to local date string "2026-04-14"
        if (!isoStr) return "";
        var d = new Date(isoStr.replace(" ", "T") + "Z");
        var y = d.getFullYear();
        var m = String(d.getMonth() + 1).padStart(2, "0");
        var dd = String(d.getDate()).padStart(2, "0");
        return y + "-" + m + "-" + dd;
    }

    function formatDateChip(dateKey) {
        // "2026-04-14" → "Apr 14"
        var d = new Date(dateKey + "T12:00:00");
        return d.toLocaleString(undefined, { month: "short", day: "numeric" });
    }

    function formatDateLabel(dateKey) {
        // "2026-04-14" → "Mon Apr 14"
        var d = new Date(dateKey + "T12:00:00");
        return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric" });
    }

    function formatTimeOnly(isoStr) {
        if (!isoStr) return "";
        var d = new Date(isoStr.replace(" ", "T") + "Z");
        return d.toLocaleString(undefined, { hour: "2-digit", minute: "2-digit" });
    }

    function formatTime(isoStr) {
        if (!isoStr) return "";
        var d = new Date(isoStr.replace(" ", "T") + "Z");
        return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    }

    function formatTimeShort(d) {
        return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    }

    function capitalize(s) {
        return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
    }

    function normalizeSlot(runType) {
        var t = (runType || "").toLowerCase();
        if (t === "morning") return "morning";
        if (t === "midday")  return "midday";
        if (t === "evening") return "evening";
        return "manual";
    }

    function updateNewsRange(elId, createdAt, hoursBack) {
        var el = document.getElementById(elId);
        if (!el || !createdAt) { if (el) el.textContent = ""; return; }
        try {
            var end   = new Date(createdAt);
            var start = new Date(end.getTime() - hoursBack * 3600 * 1000);
            el.textContent = "News: " + formatTimeShort(start) + " → " + formatTimeShort(end);
        } catch (e) { el.textContent = ""; }
    }

    // ── Tab lifecycle ──────────────────────────────────────────────────
    async function onActivate() {
        renderWeekendBanner();
        await loadLatest();
        await loadScorecardSelector();
        renderHeatmap(_evaluatedReports);
        loadAccuracy();
        loadSignalPerformance();
    }

    async function loadSignalPerformance() {
        var el = document.getElementById("analyst-signal-performance");
        if (!el) return;
        try {
            var data = await App.api("/api/analyst/signal-performance?days=30");
            renderSignalPerformance(el, data);
        } catch (e) {
            el.innerHTML = '<p class="text-muted">Signal performance unavailable</p>';
        }
    }

    function renderSignalPerformance(el, data) {
        var total = data && data.total_evaluated_picks || 0;
        if (!total || !data.per_signal || Object.keys(data.per_signal).length === 0) {
            el.innerHTML = '<p class="text-muted">Still collecting data — ' +
                total + ' evaluated picks with archived briefings so far. ' +
                'Needs at least a few days of new analyst runs.</p>';
            return;
        }

        var html = '<div style="font-size:0.75rem;color:#94a3b8;margin-bottom:0.6rem;">' +
            'Based on ' + total + ' evaluated picks in last ' + (data.days_window || 30) + ' days' +
            '</div>';

        // Per-signal stats
        html += '<div class="table-scroll"><table class="catalyst-table"><thead><tr>' +
            '<th>Signal</th><th>Accuracy</th><th>When agrees Claude</th>' +
            '<th>When disagrees Claude</th><th>Samples</th>' +
            '</tr></thead><tbody>';
        Object.keys(data.per_signal).forEach(function (sig) {
            var s = data.per_signal[sig];
            function fmtAcc(v) {
                if (v == null) return '<span class="text-muted">—</span>';
                var cls = v >= 55 ? 'text-green' : v >= 45 ? 'text-muted' : 'text-red';
                return '<span class="' + cls + '">' + v.toFixed(1) + '%</span>';
            }
            html += '<tr>' +
                '<td><strong>' + App.esc(sig) + '</strong></td>' +
                '<td>' + fmtAcc(s.signal_accuracy) + '</td>' +
                '<td>' + fmtAcc(s.when_agrees_with_claude) +
                  ' <span class="text-muted" style="font-size:0.75rem;">(' + s.agree_samples + ')</span></td>' +
                '<td>' + fmtAcc(s.when_disagrees_with_claude) +
                  ' <span class="text-muted" style="font-size:0.75rem;">(' + s.disagree_samples + ')</span></td>' +
                '<td>' + s.sample_size + '</td>' +
                '</tr>';
        });
        html += '</tbody></table></div>';

        // Agreement-bucket stats
        var agg = data.by_agreement_count || {};
        if (Object.keys(agg).length) {
            html += '<div style="margin-top:0.75rem;font-size:0.8rem;">' +
                '<span style="color:#94a3b8;">Accuracy by signal consensus:</span> ';
            Object.keys(agg).sort().forEach(function (bucket) {
                var b = agg[bucket];
                var cls = (b.accuracy || 0) >= 55 ? 'text-green' :
                          (b.accuracy || 0) >= 45 ? 'text-muted' : 'text-red';
                html += '<span style="margin-right:0.8rem;">' +
                    App.esc(bucket.replace('_', ' ')) + ': <span class="' + cls + '">' +
                    (b.accuracy != null ? b.accuracy.toFixed(0) + '%' : '—') +
                    '</span> <span class="text-muted">(' + b.sample_size + ')</span></span>';
            });
            html += '</div>';
        }
        el.innerHTML = html;
    }

    // Market filter change reloads everything
    document.getElementById("analyst-market-filter").addEventListener("change", function () {
        loadLatest();
        loadScorecardSelector().then(function () { renderHeatmap(_evaluatedReports); });
        loadAccuracy();
    });

    // Register with App
    if (window.App) {
        App.tabs    = App.tabs    || {};
        App.actions = App.actions || {};
        App.tabs["analyst-tab"]    = { activate: onActivate };
        App.actions["analyst-run"] = triggerRun;
    }
})();
