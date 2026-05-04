from flask import render_template_string, session, redirect, request, jsonify
from core.db import get_connection


# =========================================================
# SIMULATION ENGINE (DETERMINISTIC)
# =========================================================
def run_simulation(base, deltas):

    mental   = float(base["mental"]   or 0)
    physical = float(base["physical"] or 0)
    work     = float(base["work"]     or 0)
    social   = float(base["social"]   or 0)

    focus_delta   = float(deltas.get("focus",   0))   # +0 to +3 hrs
    after_delta   = float(deltas.get("after",   0))   # +0 to +3 (reduction)
    meeting_delta = float(deltas.get("meeting", 0))   # +0 to +3 (reduction)
    span_delta    = float(deltas.get("span",    0))   # -2 to +2

    # ===== IMPACT MODEL =====
    # Focus increase → better mental clarity & structured work
    mental += focus_delta * 1.5
    work   += focus_delta * 2.0

    # After-hours reduction → less burnout, better physical recovery
    mental   += after_delta * 1.0
    physical += after_delta * 1.2
    work     += after_delta * 1.5

    # Meeting reduction → more deep work, reduced cognitive overload
    mental += meeting_delta * 1.0
    work   += meeting_delta * 1.8

    # Span reduction → better work-life boundary
    physical += (-span_delta) * 0.8
    work     += (-span_delta) * 1.0

    # Clamp all to 0–100
    mental   = max(0, min(100, mental))
    physical = max(0, min(100, physical))
    work     = max(0, min(100, work))
    social   = max(0, min(100, social))

    new_ewbi = round((mental + physical + work + social) / 4, 2)

    # Derive simulated risk
    if new_ewbi >= 70:
        risk = "LOW"
    elif new_ewbi >= 40:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    # Stability estimate: if EWBI improved by >= 3 points, flag as gaining stability
    ewbi_delta = round(new_ewbi - float(base["ewbi"] or 0), 2)
    if ewbi_delta >= 3:
        stability_shift = "IMPROVING"
    elif ewbi_delta <= -3:
        stability_shift = "DECLINING"
    else:
        stability_shift = "STABLE"

    return {
        "ewbi":             new_ewbi,
        "mental":           round(mental, 2),
        "physical":         round(physical, 2),
        "work":             round(work, 2),
        "social":           round(social, 2),
        "risk":             risk,
        "stability_shift":  stability_shift,
        "ewbi_delta":       ewbi_delta,
        "mental_delta":     round(mental   - float(base["mental"]   or 0), 2),
        "physical_delta":   round(physical - float(base["physical"] or 0), 2),
        "work_delta":       round(work     - float(base["work"]     or 0), 2),
        "social_delta":     round(social   - float(base["social"]   or 0), 2),
    }


# =========================================================
# ROUTE
# =========================================================
def team_simulation(team_id):

    if "employee_id" not in session:
        return redirect("/")

    role = session.get("role")
    if role not in ["HR_HEAD", "TEAM_LEAD"]:
        return "Access Denied", 403

    back_url = "/hr/home" if role == "HR_HEAD" else "/tl/home"

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT team_name, department FROM teams WHERE team_id = %s", (team_id,))
    team_info = cursor.fetchone()
    if not team_info:
        return "Invalid Team"

    cursor.execute("SELECT MAX(DATE(date)) as latest FROM ewbi_scores")
    latest_date = cursor.fetchone()["latest"]

    cursor.execute("""
        SELECT
            ROUND(AVG(es.ewbi_score),2)             as ewbi,
            ROUND(AVG(ds.mental_score),2)        as mental,
            ROUND(AVG(ds.physical_score),2)      as physical,
            ROUND(AVG(ds.work_pattern_score),2)  as work,
            ROUND(AVG(ds.social_score),2)        as social,
            ROUND(AVG(wp.after_hours_work_hours),2) as after_hours,
            ROUND(AVG(wp.focus_hours),2)            as focus,
            ROUND(AVG(wp.meeting_hours),2)          as meeting,
            ROUND(AVG(wp.workday_span_hours),2)     as span,
            (SELECT rl.risk_level FROM risk_levels rl
             JOIN employees e2 ON rl.employee_id = e2.employee_id
             WHERE e2.team_id = %s AND DATE(rl.date) = %s
             GROUP BY rl.risk_level ORDER BY COUNT(*) DESC LIMIT 1) as risk_level,
            ROUND(SUM(CASE WHEN rl.sustained_flag=1 THEN 1 ELSE 0 END)*100.0/COUNT(rl.id),1) as stability
        FROM employees e
        JOIN ewbi_scores es ON e.employee_id = es.employee_id
        LEFT JOIN dimension_scores ds
            ON e.employee_id = ds.employee_id AND DATE(es.date) = DATE(ds.date)
        LEFT JOIN work_pattern_metrics wp
            ON e.employee_id = wp.employee_id AND DATE(es.date) = DATE(wp.date)
        LEFT JOIN risk_levels rl
            ON e.employee_id = rl.employee_id AND DATE(rl.date) = DATE(es.date)
        WHERE e.team_id = %s AND DATE(es.date) = %s
    """, (team_id, latest_date, team_id, latest_date))
    base = cursor.fetchone()

    cursor.close()
    conn.close()

    # POST — return JSON for AJAX
    if request.method == "POST":
        deltas = request.json
        result = run_simulation(base, deltas)
        return jsonify(result)

    # =============================
    # GET — full page
    # =============================
    base_risk = base.get("risk_level") or ("LOW" if (base["ewbi"] or 0) >= 70 else "MEDIUM" if (base["ewbi"] or 0) >= 40 else "HIGH")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Simulation — {{team_name}}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

            body {
                background: #07080D;
                color: #E2E8F0;
                font-family: 'Segoe UI', system-ui, sans-serif;
                padding: 28px 24px;
                min-height: 100vh;
            }

            .container { max-width: 1100px; margin: auto; }

            /* HEADER */
            .header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 28px;
                padding-bottom: 20px;
                border-bottom: 1px solid #1E2433;
            }
            .header-left h2  { font-size: 20px; font-weight: 700; color: #F1F5F9; margin-bottom: 4px; }
            .header-left p   { font-size: 13px; color: #64748B; }
            .back-btn {
                background: #1E2433;
                padding: 9px 16px;
                border-radius: 8px;
                text-decoration: none;
                color: #94A3B8;
                font-size: 13px;
                transition: background .2s;
            }
            .back-btn:hover { background: #2D3748; color: #E2E8F0; }

            /* LAYOUT */
            .main-grid {
                display: grid;
                grid-template-columns: 320px 1fr;
                gap: 20px;
                align-items: start;
            }

            /* PANEL */
            .panel {
                background: #0F1117;
                border: 1px solid #1E2433;
                border-radius: 14px;
                padding: 20px;
            }
            .panel-title {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #475569;
                margin-bottom: 16px;
            }

            /* BASELINE METRICS */
            .baseline-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-bottom: 18px;
            }
            .bm {
                background: #141820;
                border-radius: 10px;
                padding: 12px 14px;
                border-left: 3px solid #1E2433;
            }
            .bm.ewbi-card { grid-column: 1 / -1; border-color: #7C3AED; }
            .bm .bm-label { font-size: 10px; color: #64748B; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
            .bm .bm-val   { font-size: 20px; font-weight: 700; color: #F1F5F9; }
            .bm .bm-sub   { font-size: 11px; color: #475569; margin-top: 3px; }

            /* SLIDERS */
            .slider-group { margin-bottom: 18px; }
            .slider-row   { margin-bottom: 14px; }
            .slider-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            }
            .slider-label { font-size: 13px; color: #94A3B8; }
            .slider-badge {
                font-size: 12px;
                font-weight: 700;
                color: #A78BFA;
                background: #1E1535;
                padding: 2px 8px;
                border-radius: 5px;
                min-width: 48px;
                text-align: center;
            }

            input[type=range] {
                -webkit-appearance: none;
                width: 100%;
                height: 5px;
                background: #1E2433;
                border-radius: 3px;
                outline: none;
            }
            input[type=range]::-webkit-slider-thumb {
                -webkit-appearance: none;
                width: 16px; height: 16px;
                background: #7C3AED;
                border-radius: 50%;
                cursor: pointer;
                box-shadow: 0 0 0 3px #1E1535;
                transition: background .15s;
            }
            input[type=range]::-webkit-slider-thumb:hover { background: #9D5CF0; }

            .sim-btn {
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #7C3AED, #5B21B6);
                border: none;
                border-radius: 10px;
                color: white;
                font-size: 14px;
                font-weight: 700;
                cursor: pointer;
                letter-spacing: .3px;
                transition: opacity .2s, transform .1s;
                margin-top: 4px;
            }
            .sim-btn:hover   { opacity: .9; }
            .sim-btn:active  { transform: scale(.98); }

            .reset-btn {
                width: 100%;
                padding: 9px;
                background: transparent;
                border: 1px solid #1E2433;
                border-radius: 8px;
                color: #64748B;
                font-size: 13px;
                cursor: pointer;
                margin-top: 8px;
                transition: border-color .2s, color .2s;
            }
            .reset-btn:hover { border-color: #475569; color: #94A3B8; }

            /* RIGHT PANEL */
            .right-col { display: flex; flex-direction: column; gap: 16px; }

            /* DELTA TABLE */
            .delta-table { width: 100%; border-collapse: collapse; }
            .delta-table th {
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: .8px;
                color: #475569;
                text-align: left;
                padding: 8px 10px;
                border-bottom: 1px solid #1E2433;
            }
            .delta-table td {
                padding: 10px 10px;
                font-size: 14px;
                border-bottom: 1px solid #141820;
                vertical-align: middle;
            }
            .delta-table tr:last-child td { border-bottom: none; }
            .metric-name { color: #94A3B8; font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
            .val-before  { color: #64748B; }
            .val-after   { color: #F1F5F9; font-weight: 600; }
            .val-delta   { font-weight: 700; font-size: 13px; }
            .pos  { color: #10B981; }
            .neg  { color: #EF4444; }
            .neu  { color: #64748B; }

            /* RISK BADGE */
            .risk-badge {
                display: inline-block;
                padding: 3px 10px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: .3px;
            }
            .risk-LOW    { background: #052E16; color: #10B981; }
            .risk-MEDIUM { background: #2D1B00; color: #F59E0B; }
            .risk-HIGH   { background: #2D0A0A; color: #EF4444; }

            /* CHART AREA */
            .charts-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 16px;
            }
            .chart-box {
                background: #0F1117;
                border: 1px solid #1E2433;
                border-radius: 12px;
                padding: 16px;
            }
            .chart-title {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: .8px;
                color: #475569;
                margin-bottom: 12px;
            }
            .chart-wrap { position: relative; height: 200px; }

            /* IDLE STATE */
            .idle-msg {
                color: #334155;
                font-size: 13px;
                text-align: center;
                padding: 32px 0;
            }

            /* STABILITY SHIFT */
            .shift-pill {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                padding: 3px 10px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 700;
            }
            .shift-IMPROVING { background: #052E16; color: #10B981; }
            .shift-STABLE    { background: #1C1C2E; color: #818CF8; }
            .shift-DECLINING { background: #2D0A0A; color: #EF4444; }

            /* LOADING SPINNER */
            .spinner {
                display: none;
                width: 18px; height: 18px;
                border: 2px solid #ffffff44;
                border-top-color: white;
                border-radius: 50%;
                animation: spin .6s linear infinite;
                margin: 0 auto;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            /* SCENARIO PRESETS */
            .presets {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                margin-bottom: 14px;
            }
            .preset-btn {
                padding: 5px 12px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
                cursor: pointer;
                border: 1px solid;
                transition: opacity .15s;
            }
            .preset-btn:hover { opacity: .8; }
            .p-focus   { background: #0D1F3C; border-color: #3B82F6; color: #60A5FA; }
            .p-burnout { background: #1C0F2E; border-color: #A78BFA; color: #C4B5FD; }
            .p-meetings{ background: #0D2416; border-color: #10B981; color: #34D399; }
        </style>
    </head>
    <body>
    <div class="container">

        <!-- HEADER -->
        <div class="header">
            <div class="header-left">
                <h2>{{team_name}} — Intervention Simulator</h2>
                <p>{{department}} &nbsp;·&nbsp; Counterfactual analysis &nbsp;·&nbsp; As of {{latest_date}}</p>
            </div>
            <a href="{{back_url}}" class="back-btn">&#8592; Back</a>
        </div>

        <div class="main-grid">

            <!-- LEFT: CONTROLS -->
            <div>

                <!-- BASELINE -->
                <div class="panel" style="margin-bottom:16px;">
                    <div class="panel-title">Current Baseline</div>
                    <div class="baseline-grid">
                        <div class="bm ewbi-card">
                            <div class="bm-label">EWBI Score</div>
                            <div class="bm-val">{{base_ewbi}}</div>
                            <div class="bm-sub">
                                <span class="risk-badge risk-{{base_risk}}">{{base_risk}}</span>
                                &nbsp; Stability {{base_stability}}%
                            </div>
                        </div>
                        <div class="bm" style="border-color:#818CF8;">
                            <div class="bm-label">Mental</div>
                            <div class="bm-val" style="font-size:17px;">{{base_mental}}</div>
                        </div>
                        <div class="bm" style="border-color:#34D399;">
                            <div class="bm-label">Physical</div>
                            <div class="bm-val" style="font-size:17px;">{{base_physical}}</div>
                        </div>
                        <div class="bm" style="border-color:#F59E0B;">
                            <div class="bm-label">Work</div>
                            <div class="bm-val" style="font-size:17px;">{{base_work}}</div>
                        </div>
                        <div class="bm" style="border-color:#06B6D4;">
                            <div class="bm-label">Social</div>
                            <div class="bm-val" style="font-size:17px;">{{base_social}}</div>
                        </div>
                    </div>
                    <div style="font-size:11px;color:#334155;border-top:1px solid #1E2433;padding-top:12px;">
                        After-Hours: <span style="color:#64748B;">{{base_after}}h</span> &nbsp;
                        Focus: <span style="color:#64748B;">{{base_focus}}h</span> &nbsp;
                        Meetings: <span style="color:#64748B;">{{base_meeting}}h</span> &nbsp;
                        Span: <span style="color:#64748B;">{{base_span}}h</span>
                    </div>
                </div>

                <!-- CONTROLS -->
                <div class="panel">
                    <div class="panel-title">Intervention Controls</div>

                    <!-- PRESETS -->
                    <div style="font-size:10px;color:#334155;text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px;">Quick Scenarios</div>
                    <div class="presets">
                        <button class="preset-btn p-focus"    onclick="applyPreset(2,0,0,0)">&#9654; Deep Work Mode</button>
                        <button class="preset-btn p-burnout"  onclick="applyPreset(1,2,1,0)">&#9829; Burnout Recovery</button>
                        <button class="preset-btn p-meetings" onclick="applyPreset(0,0,2,0)">&#9646; Cut Meetings</button>
                    </div>

                    <div class="slider-group">

                        <div class="slider-row">
                            <div class="slider-header">
                                <span class="slider-label">&#43; Focus Hours</span>
                                <span class="slider-badge" id="lbl-focus">+0h</span>
                            </div>
                            <input type="range" id="sl-focus" min="0" max="3" step="0.5" value="0"
                                oninput="updateLabel('focus',this.value); liveSimulate()">
                        </div>

                        <div class="slider-row">
                            <div class="slider-header">
                                <span class="slider-label">&#8722; After-Hours Work</span>
                                <span class="slider-badge" id="lbl-after">-0h</span>
                            </div>
                            <input type="range" id="sl-after" min="0" max="3" step="0.5" value="0"
                                oninput="updateLabel('after',this.value); liveSimulate()">
                        </div>

                        <div class="slider-row">
                            <div class="slider-header">
                                <span class="slider-label">&#8722; Meeting Hours</span>
                                <span class="slider-badge" id="lbl-meeting">-0h</span>
                            </div>
                            <input type="range" id="sl-meeting" min="0" max="3" step="0.5" value="0"
                                oninput="updateLabel('meeting',this.value); liveSimulate()">
                        </div>

                        <div class="slider-row">
                            <div class="slider-header">
                                <span class="slider-label">&#8644; Workday Span Change</span>
                                <span class="slider-badge" id="lbl-span">0h</span>
                            </div>
                            <input type="range" id="sl-span" min="-2" max="2" step="0.5" value="0"
                                oninput="updateLabel('span',this.value,'span'); liveSimulate()">
                        </div>

                    </div>

                    <button class="sim-btn" onclick="runSimulation()">
                        <span id="btn-text">Run Simulation</span>
                        <div class="spinner" id="spinner"></div>
                    </button>
                    <button class="reset-btn" onclick="resetAll()">Reset All</button>
                </div>

            </div>

            <!-- RIGHT: OUTPUT -->
            <div class="right-col">

                <!-- DELTA TABLE -->
                <div class="panel">
                    <div class="panel-title">Impact Analysis</div>
                    <div id="idle-state" class="idle-msg">
                        Adjust sliders and run simulation to see impact
                    </div>
                    <div id="result-block" style="display:none;">
                        <table class="delta-table">
                            <thead>
                                <tr>
                                    <th>Metric</th>
                                    <th>Before</th>
                                    <th>After</th>
                                    <th>Change</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="metric-name">EWBI</td>
                                    <td class="val-before">{{base_ewbi}}</td>
                                    <td class="val-after" id="r-ewbi">—</td>
                                    <td class="val-delta" id="d-ewbi">—</td>
                                </tr>
                                <tr>
                                    <td class="metric-name">Risk</td>
                                    <td><span class="risk-badge risk-{{base_risk}}">{{base_risk}}</span></td>
                                    <td id="r-risk">—</td>
                                    <td id="d-stability">—</td>
                                </tr>
                                <tr>
                                    <td class="metric-name">Mental</td>
                                    <td class="val-before">{{base_mental}}</td>
                                    <td class="val-after" id="r-mental">—</td>
                                    <td class="val-delta" id="d-mental">—</td>
                                </tr>
                                <tr>
                                    <td class="metric-name">Physical</td>
                                    <td class="val-before">{{base_physical}}</td>
                                    <td class="val-after" id="r-physical">—</td>
                                    <td class="val-delta" id="d-physical">—</td>
                                </tr>
                                <tr>
                                    <td class="metric-name">Work</td>
                                    <td class="val-before">{{base_work}}</td>
                                    <td class="val-after" id="r-work">—</td>
                                    <td class="val-delta" id="d-work">—</td>
                                </tr>
                                <tr>
                                    <td class="metric-name">Social</td>
                                    <td class="val-before">{{base_social}}</td>
                                    <td class="val-after" id="r-social">—</td>
                                    <td class="val-delta" id="d-social">—</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- CHARTS -->
                <div class="charts-grid">
                    <div class="chart-box">
                        <div class="chart-title">EWBI — Before vs After</div>
                        <div class="chart-wrap">
                            <canvas id="ewbi-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-box">
                        <div class="chart-title">Dimension Comparison</div>
                        <div class="chart-wrap">
                            <canvas id="dim-chart"></canvas>
                        </div>
                    </div>
                </div>

            </div>
        </div>
    </div>

    <script>
    // ===== BASELINE =====
    const BASE = {
        ewbi:     {{base_ewbi}},
        mental:   {{base_mental}},
        physical: {{base_physical}},
        work:     {{base_work}},
        social:   {{base_social}},
        risk:     "{{base_risk}}"
    };

    // ===== LABEL UPDATERS =====
    function updateLabel(id, val, type) {
        const el = document.getElementById("lbl-" + id);
        if (type === 'span') {
            el.textContent = (val >= 0 ? "+" : "") + val + "h";
        } else {
            el.textContent = "+" + val + "h";
            if (id === 'after' || id === 'meeting') {
                el.textContent = "-" + val + "h";
            }
        }
    }

    function applyPreset(focus, after, meeting, span) {
        document.getElementById("sl-focus").value   = focus;
        document.getElementById("sl-after").value   = after;
        document.getElementById("sl-meeting").value = meeting;
        document.getElementById("sl-span").value    = span;
        updateLabel("focus",   focus);
        updateLabel("after",   after);
        updateLabel("meeting", meeting);
        updateLabel("span",    span, "span");
        runSimulation();
    }

    function resetAll() {
        ["focus","after","meeting","span"].forEach(id => {
            const el = document.getElementById("sl-" + id);
            el.value = 0;
        });
        updateLabel("focus", 0);
        updateLabel("after", 0);
        updateLabel("meeting", 0);
        updateLabel("span", 0, "span");
        document.getElementById("idle-state").style.display  = "block";
        document.getElementById("result-block").style.display = "none";
        if (ewbiChart) { resetCharts(); }
    }

    // ===== DEBOUNCE FOR LIVE SIMULATE =====
    let debounceTimer = null;
    function liveSimulate() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(runSimulation, 300);
    }

    // ===== CHARTS =====
    const chartOpts = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#64748B", font: { size: 11 } } } },
        scales: {
            x: { ticks: { color: "#475569", font: { size: 11 } }, grid: { color: "#1E2433" } },
            y: { min: 0, max: 100, ticks: { color: "#475569", font: { size: 11 } }, grid: { color: "#1E2433" } }
        }
    };

    let ewbiChart = new Chart(document.getElementById("ewbi-chart"), {
        type: "bar",
        data: {
            labels: ["Before", "After"],
            datasets: [{
                label: "EWBI",
                data: [BASE.ewbi, BASE.ewbi],
                backgroundColor: ["#2D1B69", "#7C3AED"],
                borderRadius: 6,
                barThickness: 48
            }]
        },
        options: { ...chartOpts }
    });

    let dimChart = new Chart(document.getElementById("dim-chart"), {
        type: "bar",
        data: {
            labels: ["Mental", "Physical", "Work", "Social"],
            datasets: [
                {
                    label: "Before",
                    data: [BASE.mental, BASE.physical, BASE.work, BASE.social],
                    backgroundColor: "#1E2433",
                    borderRadius: 4,
                    barThickness: 18
                },
                {
                    label: "After",
                    data: [BASE.mental, BASE.physical, BASE.work, BASE.social],
                    backgroundColor: "#7C3AED",
                    borderRadius: 4,
                    barThickness: 18
                }
            ]
        },
        options: { ...chartOpts }
    });

    function resetCharts() {
        ewbiChart.data.datasets[0].data = [BASE.ewbi, BASE.ewbi];
        ewbiChart.update();
        dimChart.data.datasets[1].data = [BASE.mental, BASE.physical, BASE.work, BASE.social];
        dimChart.update();
    }

    // ===== DELTA HELPER =====
    function fmtDelta(d) {
        if (d === 0) return { text: "—", cls: "neu" };
        const sign = d > 0 ? "+" : "";
        const cls  = d > 0 ? "pos" : "neg";
        return { text: sign + d, cls };
    }

    function setRiskBadge(el, risk) {
        el.innerHTML = `<span class="risk-badge risk-${risk}">${risk}</span>`;
    }

    function setShiftPill(el, shift) {
        const icons = { IMPROVING: "↑", STABLE: "→", DECLINING: "↓" };
        el.innerHTML = `<span class="shift-pill shift-${shift}">${icons[shift]} ${shift}</span>`;
    }

    // ===== MAIN SIMULATION =====
    function runSimulation() {
        const focus   = parseFloat(document.getElementById("sl-focus").value);
        const after   = parseFloat(document.getElementById("sl-after").value);
        const meeting = parseFloat(document.getElementById("sl-meeting").value);
        const span    = parseFloat(document.getElementById("sl-span").value);

        const btn  = document.getElementById("btn-text");
        const spin = document.getElementById("spinner");
        btn.style.display  = "none";
        spin.style.display = "block";

        fetch(window.location.href, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ focus, after, meeting, span })
        })
        .then(res => res.json())
        .then(data => {
            btn.style.display  = "inline";
            spin.style.display = "none";

            document.getElementById("idle-state").style.display   = "none";
            document.getElementById("result-block").style.display = "block";

            // EWBI
            document.getElementById("r-ewbi").textContent = data.ewbi;
            const ed = fmtDelta(data.ewbi_delta);
            document.getElementById("d-ewbi").textContent  = ed.text;
            document.getElementById("d-ewbi").className    = "val-delta " + ed.cls;

            // Risk
            setRiskBadge(document.getElementById("r-risk"), data.risk);
            setShiftPill(document.getElementById("d-stability"), data.stability_shift);

            // Dimensions
            const dims = ["mental","physical","work","social"];
            dims.forEach(d => {
                document.getElementById("r-" + d).textContent = data[d];
                const delta = fmtDelta(data[d + "_delta"]);
                document.getElementById("d-" + d).textContent = delta.text;
                document.getElementById("d-" + d).className   = "val-delta " + delta.cls;
            });

            // Charts
            ewbiChart.data.datasets[0].data = [BASE.ewbi, data.ewbi];
            ewbiChart.data.datasets[0].backgroundColor = [
                "#2D1B69",
                data.ewbi_delta > 0 ? "#10B981" : data.ewbi_delta < 0 ? "#EF4444" : "#7C3AED"
            ];
            ewbiChart.update();

            dimChart.data.datasets[1].data = [data.mental, data.physical, data.work, data.social];
            dimChart.update();
        })
        .catch(() => {
            btn.style.display  = "inline";
            spin.style.display = "none";
        });
    }
    </script>

    </body>
    </html>
    """

    return render_template_string(html,
        team_name    = team_info["team_name"],
        department   = team_info["department"],
        latest_date  = latest_date,
        back_url     = back_url,
        base_ewbi    = base["ewbi"]     or 0,
        base_mental  = base["mental"]   or 0,
        base_physical= base["physical"] or 0,
        base_work    = base["work"]     or 0,
        base_social  = base["social"]   or 0,
        base_after   = base["after_hours"] or 0,
        base_focus   = base["focus"]    or 0,
        base_meeting = base["meeting"]  or 0,
        base_span    = base["span"]     or 0,
        base_risk    = base_risk,
        base_stability = base["stability"] or 0,
    )