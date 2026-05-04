from flask import Blueprint, render_template_string, session, redirect, request
from core.db import get_connection

org_dashboard = Blueprint('org_dashboard', __name__)

@org_dashboard.route("/org/dashboard")
def dashboard():

    # =============================
    # AUTH
    # =============================
    if "employee_id" not in session:
        return redirect("/")

    if session.get("role") != "HR_HEAD":
        return "Access Denied", 403

    back_url = "/hr/home"

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # =============================
    # FILTER INPUT
    # =============================
    selected_departments = request.args.getlist("department")
    selected_teams = request.args.getlist("team")

    # =============================
    # FILTER OPTIONS
    # =============================
    cursor.execute("SELECT DISTINCT department FROM teams")
    departments = [r["department"] for r in cursor.fetchall()]

    cursor.execute("SELECT team_name, department FROM teams")
    rows = cursor.fetchall()

    dept_team_map = {}
    for r in rows:
        dept_team_map.setdefault(r["department"], []).append(r["team_name"])

    # =============================
    # FILTER SQL
    # =============================
    filters = []
    params = []

    if selected_departments:
        filters.append("t.department IN (%s)" % ",".join(["%s"] * len(selected_departments)))
        params.extend(selected_departments)

    if selected_teams:
        filters.append("t.team_name IN (%s)" % ",".join(["%s"] * len(selected_teams)))
        params.extend(selected_teams)

    filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

    # =============================
    # LATEST DATE
    # =============================
    cursor.execute(f"""
        SELECT MAX(DATE(es.date)) as latest_date
        FROM ewbi_scores es
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE 1=1 {filter_sql}
    """, params)

    latest_date = cursor.fetchone()["latest_date"]
    if not latest_date:
        return "No data available"

    # =============================
    # COHORT SIZE (needed for header)
    # =============================
    cursor.execute(f"""
        SELECT COUNT(DISTINCT e.employee_id) as cohort
        FROM ewbi_scores es
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE DATE(es.date) = %s {filter_sql}
    """, [latest_date] + params)

    cohort_size = cursor.fetchone()["cohort"]

    # =============================
    # HEADER LOGIC (CRITICAL)
    # =============================
    cursor.execute("SELECT COUNT(*) as total FROM employees")
    total_employees = cursor.fetchone()["total"]

    if not selected_departments and not selected_teams:
        header_title = "Organization Overview"
        header_sub = f"{total_employees} Employees"

    elif selected_teams:
        if len(selected_teams) == 1:
            header_title = selected_teams[0]
            header_sub = "Team View"
        else:
            header_title = f"{len(selected_teams)} Teams Selected"
            header_sub = f"{cohort_size} Employees"

    elif selected_departments:
        if len(selected_departments) == 1:
            header_title = selected_departments[0]
            header_sub = "Department View"
        else:
            header_title = f"{len(selected_departments)} Departments Selected"
            header_sub = f"{cohort_size} Employees"

    # =============================
    # KPI
    # =============================
    cursor.execute(f"""
        SELECT ROUND(AVG(es.ewbi_score),2) as avg_ewbi
        FROM ewbi_scores es
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE DATE(es.date) = %s {filter_sql}
    """, [latest_date] + params)

    avg_ewbi = cursor.fetchone()["avg_ewbi"] or 0

    cursor.execute(f"""
        SELECT rl.risk_level, COUNT(*) as cnt
        FROM risk_levels rl
        JOIN employees e ON rl.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE DATE(rl.date) = %s {filter_sql}
        GROUP BY rl.risk_level
        ORDER BY cnt DESC
        LIMIT 1
    """, [latest_date] + params)

    row = cursor.fetchone()
    team_risk = row["risk_level"] if row else "UNKNOWN"

    cursor.execute(f"""
        SELECT ROUND(
            SUM(CASE WHEN rl.sustained_flag=1 THEN 1 ELSE 0 END)*100.0/COUNT(*),2
        ) as stability
        FROM risk_levels rl
        JOIN employees e ON rl.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE DATE(rl.date) = %s {filter_sql}
    """, [latest_date] + params)

    stability = cursor.fetchone()["stability"] or 0

    # =============================
    # TREND
    # =============================
    cursor.execute(f"""
        SELECT DATE(es.date) as date, ROUND(AVG(es.ewbi_score),2) as avg_ewbi
        FROM ewbi_scores es
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE 1=1 {filter_sql}
        GROUP BY DATE(es.date)
        ORDER BY DATE(es.date)
    """, params)

    trend = cursor.fetchall()

    dates = [r["date"].strftime("%Y-%m-%d") for r in trend]
    ewbi = [r["avg_ewbi"] for r in trend]

    trend_delta = round(ewbi[-1] - ewbi[-2], 2) if len(ewbi) >= 2 else 0

    # =============================
    # DIMENSIONS (scaled to 100)
    # =============================
    cursor.execute(f"""
        SELECT DATE(es.date) as date,
        ROUND(AVG(ds.mental_score),2) as mental,
        ROUND(AVG(ds.physical_score),2) as physical,
        ROUND(AVG(ds.work_pattern_score),2) as work,
        ROUND(AVG(ds.social_score),2) as social
        FROM ewbi_scores es
        LEFT JOIN dimension_scores ds 
        ON es.employee_id=ds.employee_id AND DATE(es.date)=DATE(ds.date)
        JOIN employees e ON es.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE 1=1 {filter_sql}
        GROUP BY DATE(es.date)
        ORDER BY DATE(es.date)
    """, params)

    dim = cursor.fetchall()

    dim_dates = [str(r["date"]) for r in dim]
    mental   = [float(r["mental"]   or 0) for r in dim]
    physical = [float(r["physical"] or 0) for r in dim]
    work     = [float(r["work"]     or 0) for r in dim]
    social   = [float(r["social"]   or 0) for r in dim]

    # =============================
    # CONTRIBUTION (latest only)
    # =============================
    cursor.execute(f"""
        SELECT 
        ROUND(AVG(ds.mental_score),2) as mental,
        ROUND(AVG(ds.physical_score),2) as physical,
        ROUND(AVG(ds.work_pattern_score),2) as work,
        ROUND(AVG(ds.social_score),2) as social
        FROM dimension_scores ds
        JOIN employees e ON ds.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE DATE(ds.date) = %s {filter_sql}
    """, [latest_date] + params)

    c = cursor.fetchone() or {}

    contributions = [
        float(c.get("mental")   or 0),
        float(c.get("physical") or 0),
        float(c.get("work")     or 0),
        float(c.get("social")   or 0)
    ]

    # =============================
    # TEAM COMPARISON (FILTER-AWARE)
    # =============================
    query = f"""
        SELECT 
            t.team_name,
            ROUND(AVG(es.ewbi_score), 2) as avg_ewbi
        FROM teams t
        JOIN employees e ON t.team_id = e.team_id
        JOIN ewbi_scores es ON e.employee_id = es.employee_id
        WHERE DATE(es.date) = %s {filter_sql}
        GROUP BY t.team_id, t.team_name
        ORDER BY avg_ewbi DESC
    """
    
    cursor.execute(query, [latest_date] + params)
    
    comp = cursor.fetchall()
    
    comp_labels = [r["team_name"] for r in comp]
    comp_values = [float(r["avg_ewbi"] or 0) for r in comp]

    # =============================
    # WORK PATTERN TREND
    # =============================
    cursor.execute(f"""
        SELECT DATE(wpm.date) as date,
        ROUND(AVG(wpm.meeting_hours), 2) as meeting,
        ROUND(AVG(wpm.after_hours_work_hours), 2) as after_hours,
        ROUND(AVG(wpm.focus_hours), 2) as focus,
        ROUND(AVG(wpm.workday_span_hours), 2) as span
        FROM work_pattern_metrics wpm
        JOIN employees e ON wpm.employee_id = e.employee_id
        JOIN teams t ON e.team_id = t.team_id
        WHERE 1=1 {filter_sql}
        GROUP BY DATE(wpm.date)
        ORDER BY DATE(wpm.date)
    """, params)

    wp = cursor.fetchall()

    wp_dates = [str(r["date"]) for r in wp]
    meeting  = [float(r["meeting"]     or 0) for r in wp]
    after    = [float(r["after_hours"] or 0) for r in wp]
    focus    = [float(r["focus"]       or 0) for r in wp]
    span     = [float(r["span"]        or 0) for r in wp]

    cursor.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Org Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {background:#0B0B0F;color:white;font-family:Arial;padding:20px;}
            .container {max-width:1200px;margin:auto;}

            .header {
                display:flex;
                justify-content:space-between;
                align-items: flex-start;   /* 🔥 KEY FIX */
            }

            .kpi-row {
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 20px;
                padding: 10px;
            }

            .card {
                background:#111827;
                padding:20px;
                border-radius:12px;
                flex:1;
                text-align:center;
                position:relative;
                overflow:hidden;
            }

            .card::before {
                content:"";
                position:absolute;
                left:0;
                top:0;
                height:100%;
                width:5px;
                background:#7C3AED;
            }

            .value {font-size:28px;font-weight:bold;}

            .section {margin-bottom:60px;}

            .chart-box {
                background: #111827;
                padding: 10px;
                border-radius: 12px;
            }
            
            .chart-container {
                position: relative;
                width: 100%;
                height: 520px;   /* ← increase to match employee UI */
            }

            canvas {
                width: 100% !important;
                height: 100% !important;
                pointer-events: auto;
            }

            .back-btn {
                background:#374151;
                padding:10px 18px;
                border-radius:8px;
                text-decoration:none;
                color:white;
                font-weight:600;
            }

            .green { color: #10B981; }
            .red { color: #EF4444; }
            .yellow { color: #F59E0B; }

            .modal {
                display: none;
                position: fixed;
                z-index: 9999;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.75);
                justify-content: center;
                align-items: center;
                pointer-events: auto;
            }

            .modal.open {
                display: flex;
            }

            .modal-content {
                background: #111827;
                width: 420px;
                max-height: 80vh;           /* 🔥 LIMIT HEIGHT */
                overflow-y: auto;           /* 🔥 SCROLL INSIDE */
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 0 30px rgba(0,0,0,0.6);

                position: relative;
                z-index: 10000;
            }
        </style>
    </head>

    <body>

        <div class="container">

            <!-- HEADER -->
            <div class="header">
                <div>
                    <h2>{{header_title}}</h2>
                    <p style="color:#9CA3AF;">{{header_sub}}</p>
                </div>

                <div style="display:flex; gap:10px;">
                    <button type="button" onclick="openFilter()" style="
                        background:#7C3AED; padding:10px 16px; border:none; border-radius:8px; color:white; cursor:pointer;">
                        Filter
                    </button>

                    <button type="button" onclick="resetFilters()" style="
                        background:#374151; padding:10px 16px; border:none; border-radius:8px; color:white; cursor:pointer;">
                        Reset
                    </button>

                    <a href="{{back_url}}" class="back-btn">Back</a>
                </div>
            </div>

            <!-- FILTER MODAL -->
            <div id="filterModal" class="modal">
                <div class="modal-content">

                    <h3>Filters</h3>

                    <!-- DEPARTMENT -->
                    <div>
                        <h4>Department</h4>
                        <div id="deptList">
                            {% for d in departments %}
                                <label>
                                    <input type="checkbox" class="dept" value="{{d}}"
                                    {% if d in selected_departments %}checked{% endif %}>
                                    {{d}}
                                </label><br>
                            {% endfor %}
                        </div>
                    </div>

                    <!-- TEAM -->
                    <div style="margin-top:20px;">
                        <h4>Team</h4>
                        <div id="teamList">
                            {% for d, teams in dept_team_map.items() %}
                                {% for t in teams %}
                                    <label data-dept="{{d}}">
                                        <input type="checkbox" class="team" value="{{t}}"
                                        {% if t in selected_teams %}checked{% endif %}>
                                        {{t}}
                                    </label><br>
                                {% endfor %}
                            {% endfor %}
                        </div>
                    </div>

                    <!-- ACTIONS -->
                    <div style="margin-top:20px;">
                        <button type="button" onclick="applyFilters()">Apply</button>
                        <button type="button" onclick="clearFilters()">Clear</button>
                        <button type="button" onclick="closeFilter()">Close</button>
                    </div>

                </div>
            </div>

            <!-- DATE -->
            <div style="margin-bottom:10px;color:#9CA3AF;">
                As of {{latest_date}}
            </div>

            <!-- KPI -->
            <div class="kpi-row">
                <div class="card">
                    <div>Avg EWBI</div>
                    <div class="value">{{avg_ewbi}}</div>
                </div>

                <div class="card 
                {% if team_risk == 'LOW' %}green
                {% elif team_risk == 'MEDIUM' %}yellow
                {% else %}red{% endif %}">
                    <div>Team Risk</div>
                    <div class="value">{{team_risk}}</div>
                </div>

                <div class="card">
                    <div>Cohort Size</div>
                    <div class="value">{{cohort_size}}</div>
                </div>

                <div class="card 
                {% if trend_delta > 0 %}green
                {% elif trend_delta < 0 %}red
                {% else %}yellow{% endif %}">
                    <div>Trend</div>
                    <div class="value">
                        {% if trend_delta > 0 %}
                            ↑ {{trend_delta}}
                        {% elif trend_delta < 0 %}
                            ↓ {{trend_delta}}
                        {% else %}
                            — 0
                        {% endif %}
                    </div>
                </div>

                <div class="card 
                {% if stability >= 70 %}green
                {% elif stability >= 40 %}yellow
                {% else %}red{% endif %}">
                    <div>Stability</div>
                    <div class="value">
                        {% if stability >= 70 %} ✔
                        {% elif stability >= 40 %} ⚠
                        {% else %} ✖
                        {% endif %}
                        <br>
                        {{stability}}%
                    </div>
                </div>
            </div>

            <!-- CHARTS -->
            <div class="chart-box">
                <h3>Average EWBI Trend</h3>
                <div class="chart-container">
                    <canvas id="ewbiChart"></canvas>
                </div>
            </div>

            <div class="chart-box">
                <h3>Average Dimension Trends</h3>
                <div class="chart-container">
                    <canvas id="dimChart"></canvas>
                </div>
            </div>

            <div class="section" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div class="chart-box">
                    <h3>Contribution</h3>
                    <div class="chart-container">
                        <canvas id="donutChart"></canvas>
                    </div>
                </div>

                <div class="chart-box">
                    <h3>Team Comparison</h3>
                    <div class="chart-container">
                        <canvas id="barChart"></canvas>
                    </div>
                </div>
            </div>

            <div class="chart-box">
                <h3>Team Work Pattern</h3>
                <div class="chart-container">
                    <canvas id="wpChart"></canvas>
                </div>
            </div>

        </div>
    
    <script>

        const baseOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "white" } }
            }
        };

        // =======================
        // EWBI (0–100)
        // =======================
        const ewbiData = {{ewbi|tojson}};
        const ewbiMin = Math.floor(Math.min(...ewbiData));
        const ewbiMax = Math.ceil(Math.max(...ewbiData));

        new Chart(document.getElementById('ewbiChart'), {
            type: 'line',
            data: {
                labels: {{dates|tojson}},
                datasets: [{
                    label: 'EWBI',
                    data: ewbiData,
                    borderColor: '#7C3AED',
                    tension: 0.4,
                    fill: false,
                    spanGaps: true
                }]
            },
            options: {
                ...baseOptions,
                scales: {
                    x: {
                        ticks: { color: "white", maxTicksLimit: 10 }
                    },
                    y: {
                        min: ewbiMin,
                        max: ewbiMax,
                        ticks: { color: "white", stepSize: 2 }
                    }
                }
            }
        });

        // =======================
        // DIMENSIONS (0–100)
        // =======================
        const dimAllData = [{{mental|tojson}}, {{physical|tojson}}, {{work|tojson}}, {{social|tojson}}].flat();
        const dimMin = Math.floor(Math.min(...dimAllData));
        const dimMax = Math.ceil(Math.max(...dimAllData));

        new Chart(document.getElementById('dimChart'), {
            type: 'line',
            data: {
                labels: {{dim_dates|tojson}},
                datasets: [
                    { label: 'Mental', data: {{mental|tojson}}, borderColor: '#7C3AED', fill:false },
                    { label: 'Physical', data: {{physical|tojson}}, borderColor: '#3B82F6', fill:false },
                    { label: 'Work', data: {{work|tojson}}, borderColor: '#F59E0B', fill:false },
                    { label: 'Social', data: {{social|tojson}}, borderColor: '#06B6D4', fill:false }
                ]
            },
            options: {
                ...baseOptions,
                scales: {
                    x: { ticks: { color: "white", maxTicksLimit: 10 } },
                    y: { min: dimMin, max: dimMax, ticks: { color: "white", stepSize: 2 } }
                }
            }
        });

        // =======================
        // DONUT (NO SCALES)
        // =======================
        new Chart(document.getElementById('donutChart'), {
            type: 'doughnut',
            data: {
                labels: ['Mental','Physical','Work','Social'],
                datasets: [{
                    data: {{contributions|tojson}},
                    backgroundColor: ['#7C3AED','#3B82F6','#F59E0B','#06B6D4'],
                    borderWidth: 2
                }]
            },
            options: baseOptions
        });

        // =======================
        // BAR (TEAM COMPARISON)
        // =======================
        new Chart(document.getElementById('barChart'), {
            type: 'bar',
            data: {
                labels: {{comp_labels|tojson}},
                datasets: [{
                    label: "EWBI",
                    data: {{comp_values|tojson}},
                    backgroundColor: '#10B981'
                }]
            },
            options: {
                ...baseOptions,
                scales: {
                    x: {
                        ticks: {
                            color: "white",
                            autoSkip: false,
                            maxRotation: 60,
                            minRotation: 45
                        }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        ticks: { color: "white" }
                    }
                }
            }
        });

        // =======================
        // WORK PATTERN (0–12 hrs)
        // =======================
        new Chart(document.getElementById('wpChart'), {
            type: 'line',
            data: {
                labels: {{wp_dates|tojson}},
                datasets: [
                    { label:'Meeting', data:{{meeting|tojson}}, borderColor:'#EF4444', fill:false },
                    { label:'After Hours', data:{{after|tojson}}, borderColor:'#F59E0B', fill:false },
                    { label:'Focus', data:{{focus|tojson}}, borderColor:'#10B981', fill:false },
                    { label:'Span', data:{{span|tojson}}, borderColor:'#3B82F6', fill:false }
                ]
            },
            options: {
                ...baseOptions,
                scales: {
                    x: { ticks: { color: "white", maxTicksLimit: 10 } },
                    y: {
                        min: 0,
                        max: 12,
                        ticks: { color: "white" }
                    }
                }
            }
        });

        // =======================
        // FILTER MODAL
        // =======================
        function openFilter() {
            const modal = document.getElementById("filterModal");
            modal.classList.add("open");
            document.body.style.overflow = "hidden";
        }

        function closeFilter() {
            document.getElementById("filterModal").classList.remove("open");
            document.body.style.overflow = "auto";
        }

        document.getElementById("filterModal").addEventListener("click", function(e) {
            if (e.target === this) closeFilter();
        });

        // prevent inside click
        document.querySelector(".modal-content").addEventListener("click", function(e) {
            e.stopPropagation();
        });

        // =======================
        // FILTER LOGIC
        // =======================
        function updateTeams() {
            let selectedDepts = [...document.querySelectorAll(".dept:checked")]
                .map(x => x.value);

            document.querySelectorAll("#teamList label").forEach(label => {
                let dept = label.getAttribute("data-dept");

                if (selectedDepts.length === 0 || selectedDepts.includes(dept)) {
                    label.style.display = "block";
                } else {
                    label.style.display = "none";
                    label.querySelector("input").checked = false;
                }
            });
        }

        function resetFilters() {
            window.location.href = window.location.pathname;
        }

        function applyFilters() {
            let depts = [...document.querySelectorAll(".dept:checked")].map(x => x.value);
            let teams = [...document.querySelectorAll(".team:checked")].map(x => x.value);

            let url = new URL(window.location.href);
            url.search = "";

            depts.forEach(d => url.searchParams.append("department", d));
            teams.forEach(t => url.searchParams.append("team", t));

            window.location.href = url.toString();
        }

        function clearFilters() {
            document.querySelectorAll("input[type=checkbox]").forEach(cb => cb.checked = false);
            updateTeams();
        }

        // SINGLE listener only
        document.addEventListener("change", function(e) {
            if (e.target.classList.contains("dept")) {
                document.querySelectorAll(".team").forEach(t => t.checked = false);
                updateTeams();
            }
        });

        // INIT FIX
        updateTeams();

        </script>

    </body>
    </html>
    """
    # =============================
    # RENDER
    # =============================
    return render_template_string(html,
        back_url=back_url,
        header_title=header_title,
        header_sub=header_sub,
        
        departments=departments,
        dept_team_map=dept_team_map,
        selected_departments=selected_departments,
        selected_teams=selected_teams,

        latest_date=latest_date,
        avg_ewbi=avg_ewbi,
        team_risk=team_risk,
        cohort_size=cohort_size,
        trend_delta=trend_delta,
        stability=stability,

        dates=dates,
        ewbi=ewbi,

        dim_dates=dim_dates,
        mental=mental,
        physical=physical,
        work=work,
        social=social,

        contributions=contributions,

        comp_labels=comp_labels,
        comp_values=comp_values,

        wp_dates=wp_dates,
        meeting=meeting,
        after=after,
        focus=focus,
        span=span
    )