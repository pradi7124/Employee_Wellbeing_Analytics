from flask import Blueprint, render_template_string, session, redirect, request
from core.db import get_connection
import json

team_dashboard = Blueprint('team_dashboard', __name__)

@team_dashboard.route("/team/dashboard")
def dashboard():

    if "employee_id" not in session:
        return redirect("/")

    manager_id = session["employee_id"]
    role = session.get("role")
    if not role:
        return redirect("/") 
    print("ROLE IN SESSION:", role)
    ROLE_HOME_MAP = {
        "TEAM_LEAD": "/tl/home",
        "HR_HEAD": "/hr/home"
    }
    back_url = ROLE_HOME_MAP.get(role, "/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    selected_locations = request.args.getlist("location")
    selected_roles = request.args.getlist("role")
    
    # ============================================
    # TEAM META
    # ============================================
    cursor.execute("""
    SELECT team_id, team_name, department
    FROM teams
    WHERE manager_id = %s
    """, (manager_id,))
    team = cursor.fetchone()

    team_id = team["team_id"]

    # ✅ GET LOCATIONS
    cursor.execute("""
    SELECT DISTINCT location 
    FROM employees 
    WHERE team_id = %s
    """, (team_id,))
    locations = [r["location"] for r in cursor.fetchall()]

    # ✅ GET ROLES
    cursor.execute("""
    SELECT DISTINCT role 
    FROM employees 
    WHERE team_id = %s
    """, (team_id,))
    roles = [r["role"] for r in cursor.fetchall()]

    filters = []
    params = [team_id]

    # LOCATION FILTER
    if selected_locations:
        filters.append("e.location IN (%s)" % ",".join(["%s"] * len(selected_locations)))
        params.extend(selected_locations)

    # ROLE FILTER
    if selected_roles:
        filters.append("e.role IN (%s)" % ",".join(["%s"] * len(selected_roles)))
        params.extend(selected_roles)

    # FINAL SQL PART
    filter_sql = ""
    if filters:
        filter_sql = " AND " + " AND ".join(filters)

    cursor.execute("""
    SELECT location, role FROM employees WHERE team_id = %s
    """, (team_id,))
    rows = cursor.fetchall()
    
    employee_map = {}
    for r in rows:
        employee_map.setdefault(r["location"], set()).add(r["role"])
    
    employee_map = {k:list(v) for k,v in employee_map.items()}

    # ============================================
    # LATEST SNAPSHOT
    # ============================================
    cursor.execute("""
    SELECT *
    FROM team_dashboard_view
    WHERE team_id = %s
    ORDER BY date DESC
    LIMIT 1
    """, (team_id,))
    latest = cursor.fetchone()

    cursor.execute(f"""
    SELECT COUNT(DISTINCT e.employee_id) AS cohort_size
    FROM employees e
    JOIN ewbi_scores es ON e.employee_id = es.employee_id
    WHERE e.team_id = %s
    {filter_sql}
    AND es.date = %s
    """, params + [latest["date"]])

    cohort_size = cursor.fetchone()["cohort_size"] or 0

    # ============================================
    # EWBI TREND
    # ============================================
    query = f"""
    SELECT es.date, AVG(es.ewbi_score) as avg_ewbi
    FROM ewbi_scores es
    JOIN employees e ON es.employee_id = e.employee_id
    WHERE e.team_id = %s
    {filter_sql}
    GROUP BY es.date
    ORDER BY es.date
    """
    cursor.execute(query, params)
    trend = cursor.fetchall()

    dates = [str(r["date"]) for r in trend]
    ewbi = [float(r["avg_ewbi"] or 0) for r in trend]

    # ============================================
    # DIMENSION TREND
    # ============================================
    query = f"""
    SELECT es.date,
           AVG(ds.mental_score) as avg_mental,
           AVG(ds.physical_score) as avg_physical,
           AVG(ds.work_pattern_score) as avg_work_pattern,
           AVG(ds.social_score) as avg_social
    FROM ewbi_scores es
    JOIN employees e ON es.employee_id = e.employee_id
    JOIN dimension_scores ds 
      ON es.employee_id = ds.employee_id AND es.date = ds.date
    WHERE e.team_id = %s
    {filter_sql}
    GROUP BY es.date
    ORDER BY es.date
    """
    cursor.execute(query, params)
    dim = cursor.fetchall()

    dim_dates = [str(r["date"]) for r in dim]
    mental = [float(r["avg_mental"] or 0) for r in dim]
    physical = [float(r["avg_physical"] or 0) for r in dim]
    work = [float(r["avg_work_pattern"] or 0) for r in dim]
    social = [float(r["avg_social"] or 0) for r in dim]

    # ============================================
    # CONTRIBUTION
    # ============================================
    query = f"""
    SELECT 
        AVG(ds.mental_score) as mental,
        AVG(ds.physical_score) as physical,
        AVG(ds.work_pattern_score) as work,
        AVG(ds.social_score) as social
    FROM dimension_scores ds
    JOIN employees e ON ds.employee_id = e.employee_id
    WHERE e.team_id = %s
    {filter_sql}
    AND ds.date = %s
    """
    cursor.execute(query, params + [latest["date"]])
    c = cursor.fetchone()

    contributions = [
        float(c["mental"] or 0),
        float(c["physical"] or 0),
        float(c["work"] or 0),
        float(c["social"] or 0)
    ]

    # ============================================
    # TEAM COMPARISON
    # ============================================
    cursor.execute("""
    SELECT team_name, avg_ewbi
    FROM team_dashboard_view
    WHERE department = %s AND date = %s
    """, (team["department"], latest["date"]))

    comp = cursor.fetchall()
    comp_labels = [r["team_name"] for r in comp]
    comp_values = [float(r["avg_ewbi"] or 0) for r in comp]

    # ============================================
    # WORK PATTERN TREND
    # ============================================
    query = f"""
    SELECT date,
           AVG(meeting_hours) as meeting,
           AVG(after_hours_work_hours) as after_hours,
           AVG(focus_hours) as focus,
           AVG(workday_span_hours) as span
    FROM work_pattern_metrics wp
    JOIN employees e ON wp.employee_id = e.employee_id
    WHERE e.team_id = %s
    {filter_sql}
    GROUP BY date
    ORDER BY date
    """
    cursor.execute(query, params)
    wp = cursor.fetchall()

    wp_dates = [str(r["date"]) for r in wp]
    meeting = [float(r["meeting"] or 0) for r in wp]
    after = [float(r["after_hours"] or 0) for r in wp]
    focus = [float(r["focus"] or 0) for r in wp]
    span = [float(r["span"] or 0) for r in wp]

    cursor.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Team Dashboard</title>
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
                z-index: 9999;              /* 🔥 FORCE TOP */
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.75);

                display: flex;              /* 🔥 CENTERING */
                justify-content: center;
                align-items: center;
                pointer-events: auto;
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

        <div class="header">
            <div>
                <h2>{{team_name}}</h2>
                <p>{{department}}</p>
                <p>ID: {{team_id}}</p>
            </div>

            <button onclick="openFilter()" style="
            background:#7C3AED; padding:10px 16px; border:none; border-radius:8px; color:white; cursor:pointer;">
            Filter
            </button>

            <button onclick="resetFilters()" style="
            background:#374151;padding:10px 16px;border:none;border-radius:8px;color:white;cursor:pointer;">
            Reset
            </button>

            <a href="{{back_url}}" class="back-btn">Back</a>
        </div>

        <div id="filterModal" class="modal">

            <div class="modal-content">

                <h3>Filters</h3>

                <!-- LOCATION -->
                <div>
                    <h4>Location</h4>
                    <div id="locationList">
                        {% for loc in locations %}
                            <label>
                                <input type="checkbox" class="loc" value="{{loc}}">
                                {{loc}}
                            </label><br>
                        {% endfor %}
                    </div>
                </div>

                <!-- ROLE -->
                <div style="margin-top:20px;">
                    <h4>Role</h4>
                    <div id="roleList">
                        {% for r in roles %}
                            <label>
                                <input type="checkbox" class="role" value="{{r}}">
                                {{r}}
                            </label><br>
                        {% endfor %}
                    </div>
                </div>

        <div style="margin-top:20px;">
            <button onclick="applyFilters()">Apply</button>
            <button onclick="clearFilters()">Clear</button>
            <button onclick="closeFilter()">Close</button>
        </div>

    </div>
</div>

        <div style="margin-bottom:10px;color:#9CA3AF;">
            As of {{latest.date}}
        </div>

        <!-- KPI -->
        <div class="kpi-row">
            <div class="card"><div>Avg EWBI</div><div class="value">{{latest.avg_ewbi}}</div></div>
            <div class="card 
            {% if latest.team_risk == 'LOW' %}green
            {% elif latest.team_risk == 'MEDIUM' %}yellow
            {% else %}red{% endif %}">

                <div>Team Risk</div>

                <div class="value 
                {% if latest.team_risk == 'LOW' %}green
                {% elif latest.team_risk == 'MEDIUM' %}yellow
                {% else %}red{% endif %}">
                    {{latest.team_risk}}
                </div>
            </div>
            <div class="card">
                <div>Cohort Size</div>
                <div class="value">{{cohort_size}}</div>
            </div>
            <div class="card 
            {% if latest.trend_delta > 0 %}green
            {% elif latest.trend_delta < 0 %}red
            {% else %}yellow{% endif %}">
            
                <div>Trend</div>
            
                <div class="value 
                {% if latest.trend_delta > 0 %}green
                {% elif latest.trend_delta < 0 %}red
                {% else %}yellow{% endif %}">
            
                    {% if latest.trend_delta > 0 %}
                        ↑ {{latest.trend_delta}}
                    {% elif latest.trend_delta < 0 %}
                        ↓ {{latest.trend_delta}}
                    {% else %}
                        — 0
                    {% endif %}
            
                </div>
            </div>
            <div class="card 
            {% if latest.sustained_pct >= 70 %}green
            {% elif latest.sustained_pct >= 40 %}yellow
            {% else %}red{% endif %}">

                <div>Stability</div>

                <div class="value">

                    {% if latest.sustained_pct >= 70 %}
                        ✔
                    {% elif latest.sustained_pct >= 40 %}
                        ⚠
                    {% else %}
                        ✖
                    {% endif %}

                    <br>

                    {{latest.sustained_pct}}%

                </div>
            </div>
        </div>

        <!-- EWBI TREND -->
        <div class="chart-box">
            <h3>Average EWBI Trend</h3>
            <div class="chart-container">
                <canvas id="ewbiChart"></canvas>
            </div>
        </div>

        <!-- DIMENSION -->
        <div class="chart-box">
            <h3>Average Dimension Trends</h3>
            <div class="chart-container">
                <canvas id="dimChart"></canvas>
            </div>
        </div>

        <!-- GRID -->
        <div class="section" style="display:grid;grid-template-columns:1fr 1fr;align-items: stretch;gap:20px;">

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

        <!-- WORK PATTERN -->
        <div class="chart-box">
            <h3>Team Work Pattern</h3>
            <div class="chart-container">
                <canvas id="wpChart"></canvas>
            </div>
        </div>

    </div>

    <script>

    const common = {
        responsive:true,
        maintainAspectRatio:false,
        plugins:{legend:{labels:{color:"white"}}}
    };

    new Chart(document.getElementById('ewbiChart'), {
        type:'line',
        data:{labels:{{dates|safe}},datasets:[{label:'EWBI',data:{{ewbi|safe}},borderColor:'#7C3AED',tension:0.4}]},
        options:common
    });

    new Chart(document.getElementById('dimChart'), {
        type:'line',
        data:{
            labels:{{dim_dates|safe}},
            datasets:[
                {label:'Mental',data:{{mental|safe}},borderColor:'#7C3AED'},
                {label:'Physical',data:{{physical|safe}},borderColor:'#3B82F6'},
                {label:'Work',data:{{work|safe}},borderColor:'#F59E0B'},
                {label:'Social',data:{{social|safe}},borderColor:'#06B6D4'}
            ]
        },
        options:common
    });

    new Chart(document.getElementById('donutChart'), {
        type:'doughnut',
        data:{
            labels:['Mental','Physical','Work','Social'],
            datasets:[{data:{{contributions|safe}},backgroundColor:['#7C3AED','#3B82F6','#F59E0B','#06B6D4']}]
        },
        options:common
    });

    new Chart(document.getElementById('barChart'), {
        type:'bar',
        data:{
            labels:{{comp_labels|safe}},
            datasets:[{data:{{comp_values|safe}},backgroundColor:'#10B981'}]
        },
        options:common
    });

    new Chart(document.getElementById('wpChart'), {
        type:'line',
        data:{
            labels:{{wp_dates|safe}},
            datasets:[
                {label:'Meeting',data:{{meeting|safe}},borderColor:'#EF4444'},
                {label:'After Hours',data:{{after|safe}},borderColor:'#F59E0B'},
                {label:'Focus',data:{{focus|safe}},borderColor:'#10B981'},
                {label:'Span',data:{{span|safe}},borderColor:'#3B82F6'}
            ]
        },
        options:common
    });

    const empMap = {{employee_map|safe}};

        function openFilter() {
            const modal = document.getElementById("filterModal");
            modal.style.display = "flex";   // 🔥 NOT block
            document.getElementById("filterModal").style.display = "flex";
            document.body.style.overflow = "hidden";   // lock scroll
        }
        
        function closeFilter() {
            document.getElementById("filterModal").style.display = "none";
            document.body.style.overflow = "auto";
        }

        window.onclick = function(e) {
            const modal = document.getElementById("filterModal");
            if (e.target === modal) {
                closeFilter();
            }
        }
        
        // 🔥 DEPENDENCY LOGIC
        function updateRoles() {
            let selectedLocs = [...document.querySelectorAll(".loc:checked")]
                                .map(x => x.value);

            let validRoles = new Set();

            selectedLocs.forEach(loc => {
                (empMap[loc] || []).forEach(r => validRoles.add(r));
            });

            document.querySelectorAll(".role").forEach(cb => {
                cb.parentElement.style.display =
                    (selectedLocs.length === 0 || validRoles.has(cb.value))
                    ? "block" : "none";
            });
        }

        function updateLocations() {
            let selectedRoles = [...document.querySelectorAll(".role:checked")]
                                .map(x => x.value);

            let validLocs = new Set();

            for (let loc in empMap) {
                let roles = empMap[loc];
                if (selectedRoles.length === 0 || roles.some(r => selectedRoles.includes(r))) {
                    validLocs.add(loc);
                }
            }

            document.querySelectorAll(".loc").forEach(cb => {
                cb.parentElement.style.display =
                    (selectedRoles.length === 0 || validLocs.has(cb.value))
                    ? "block" : "none";
            });
        }

        function resetFilters() {
            window.location.href = window.location.pathname;
        }

        // attach listeners
        document.addEventListener("change", function(e){
            if (e.target.classList.contains("loc")) updateRoles();
            if (e.target.classList.contains("role")) updateLocations();
        });

        // APPLY
        function applyFilters() {
            let locs = [...document.querySelectorAll(".loc:checked")].map(x=>x.value);
            let roles = [...document.querySelectorAll(".role:checked")].map(x=>x.value);

            let url = new URL(window.location.href);
            url.search = "";

            locs.forEach(l => url.searchParams.append("location", l));
            roles.forEach(r => url.searchParams.append("role", r));

            window.location.href = url.toString();
        }

        // CLEAR
        function clearFilters() {
            document.querySelectorAll("input[type=checkbox]").forEach(cb=>cb.checked=false);
            updateRoles();
            updateLocations();
        }
    </script>

    </body>
    </html>
    """

    

    return render_template_string(
        html,
        team_name=team["team_name"],
        department=team["department"],
        team_id=team_id,
        latest=latest,
        locations=locations,
        roles=roles,
        selected_locations=selected_locations,
        selected_roles=selected_roles,
        back_url=back_url,
        cohort_size=cohort_size,
        dates=json.dumps(dates),
        ewbi=json.dumps(ewbi),
        dim_dates=json.dumps(dim_dates),
        mental=json.dumps(mental),
        physical=json.dumps(physical),
        work=json.dumps(work),
        social=json.dumps(social),
        contributions=json.dumps(contributions),
        comp_labels=json.dumps(comp_labels),
        comp_values=json.dumps(comp_values),
        wp_dates=json.dumps(wp_dates),
        meeting=json.dumps(meeting),
        after=json.dumps(after),
        focus=json.dumps(focus),
        span=json.dumps(span),
        employee_map=json.dumps(employee_map)
    )

    