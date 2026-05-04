from flask import Blueprint, render_template_string, session, redirect
from core.db import get_connection
import json

employee_dashboard = Blueprint('employee_dashboard', __name__)


@employee_dashboard.route("/employee/dashboard")
def dashboard():

    if "employee_id" not in session:
        return redirect("/")

    emp_id = session["employee_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ============================================
    # 1. EMPLOYEE INFO + LATEST SNAPSHOT
    # ============================================
    cursor.execute("""
    SELECT *
    FROM employee_dashboard_view
    WHERE employee_id = %s
    ORDER BY date DESC
    LIMIT 1
    """, (emp_id,))
    latest = cursor.fetchone()

    # ============================================
    # 2. EWBI TREND
    # ============================================
    cursor.execute("""
    SELECT date, ewbi_score
    FROM employee_dashboard_view
    WHERE employee_id = %s
    ORDER BY date
    """, (emp_id,))
    trend = cursor.fetchall()

    dates = [str(r["date"]) for r in trend]
    ewbi = [float(r["ewbi_score"]) for r in trend]

    # ============================================
    # 2.1 DIMENSION TREND
    # ============================================
    cursor.execute("""
    SELECT date, mental_score, physical_score, work_pattern_score, social_score
    FROM dimension_scores
    WHERE employee_id = %s
    ORDER BY date
    """, (emp_id,))
    dim = cursor.fetchall()

    dim_dates = [str(r["date"]) for r in dim]
    mental = [r["mental_score"] for r in dim]
    physical = [r["physical_score"] for r in dim]
    work = [r["work_pattern_score"] for r in dim]
    social = [r["social_score"] for r in dim]


    # ============================================
    # 2.2 CONTRIBUTION (DONUT)
    # ============================================
    contributions = [
        latest["mental_contribution"],
        latest["physical_contribution"],
        latest["work_pattern_contribution"],
        latest["social_contribution"]
    ]


    # ============================================
    # 2.3 TEAM / DEPT COMPARISON
    # ============================================
    cursor.execute("""
    SELECT e.team_id, t.department, e.location
    FROM employees e
    JOIN teams t ON e.team_id = t.team_id
    WHERE e.employee_id = %s
    """, (emp_id,))
    meta = cursor.fetchone()

    team_id = meta["team_id"]
    dept = meta["department"]
    location = meta["location"]
    date = latest["date"]

    emp_score = latest["ewbi_score"]

    # TEAM AVG
    cursor.execute("""
    SELECT AVG(es.ewbi_score) as avg_team
    FROM ewbi_scores es
    JOIN employees e ON es.employee_id = e.employee_id
    WHERE e.team_id = %s AND es.date = %s
    """, (team_id, date))
    team_avg = cursor.fetchone()["avg_team"]

    # DEPT AVG
    cursor.execute("""
    SELECT AVG(es.ewbi_score) as avg_dept
    FROM ewbi_scores es
    JOIN employees e ON es.employee_id = e.employee_id
    JOIN teams t ON e.team_id = t.team_id
    WHERE t.department = %s AND es.date = %s
    """, (dept, date))
    dept_avg = cursor.fetchone()["avg_dept"]

    # ============================================
    # 3. WORK PATTERN TREND
    # ============================================
    cursor.execute("""
    SELECT date, meeting_hours, after_hours_work_hours, focus_hours, workday_span_hours
    FROM work_pattern_metrics
    WHERE employee_id = %s
    ORDER BY date
    """, (emp_id,))
    wp = cursor.fetchall()

    wp_dates = [str(r["date"]) for r in wp]
    meeting = [r["meeting_hours"] or 0 for r in wp]
    after = [r["after_hours_work_hours"] or 0 for r in wp]
    focus = [r["focus_hours"] or 0 for r in wp]
    span = [r["workday_span_hours"] or 0 for r in wp]

    cursor.close()
    conn.close()

    # ============================================
    # TEXT INSIGHTS (BASIC LOGIC)
    # ============================================
    insights = []

    if latest["trend_delta"] and latest["trend_delta"] < 0:
        insights.append("Declining trend detected in recent cycle")

    if latest["work_pattern_score"] > 85:
        insights.append("Work pattern load is high")

    if latest["sustained_flag"] == 0:
        insights.append("Improvement not sustained")

    # ============================================
    # HTML TEMPLATE (INLINE)
    # ============================================

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Employee Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {
                background: #0B0B0F;
                color: white;
                font-family: Arial;
                margin: 0;
                padding: 20px;
            }

            .container {
                max-width: 1200px;
                margin: auto;
            }

            .header {
                margin-bottom: 25px;
            }

            .header h2 {
                color: #FFFFFF;
            }

            .header p {
                font-size: 14px;
            }

            .kpi-row {
                display: flex;
                gap: 20px;
                margin-bottom: 30px;
            }

            .card {
                background: #111827;
                padding: 20px;
                border-radius: 12px;
                flex: 1;
                text-align: center;
                position: relative;
                overflow: hidden;
            }

            /* Accent bar base */
            .card::before {
                content: "";
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                width: 5px;
                border-radius: 12px 0 0 12px;
            }

            /* Variants */
            .card.green::before {
                background: #10B981;
            }

            .card.red::before {
                background: #EF4444;
            }

            .card.yellow::before {
                background: #F59E0B;
            }

            .card.violet::before {
                background: #7C3AED;
            }

            .value {
                font-size: 28px;
                font-weight: bold;
            }

            .green { color: #10B981; }
            .red { color: #EF4444; }
            .yellow { color: #F59E0B; }

            .section {
                margin-bottom: 40px;
            }

            canvas {
                background: #111827;
                padding: 15px;
                border-radius: 12px;
            }

            .insights {
                background: #111827;
                padding: 15px;
                border-left: 4px solid #7C3AED;
                border-radius: 8px;
            }

            .chart-box {
                background: #111827;
                padding: 15px;
                border-radius: 12px;
            }

            /* FORCE SAME HEIGHT */
            .chart-container {
                height: 300px;   /* 🔥 control here */
                position: relative;
            }

            .logout-btn {
                background: #EF4444;
                color: white;
                padding: 10px 18px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                transition: 0.3s;
            }

            .logout-btn:hover {
                background: #DC2626;
            }

            .insights-btn {
                background: linear-gradient(135deg, #7C3AED, #4C1D95);
                color: white;
                padding: 12px 22px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: 600;
                transition: 0.3s;
            }
            
            .insights-btn:hover {
                background: linear-gradient(135deg, #6D28D9, #3B0764);
            }

        </style>
    </head>
    <body>

    <div class="container">

        <div class="header" style="display:flex; justify-content:space-between; align-items:flex-start;">

            <div>
                <h2 style="font-size: 26px; font-weight: 600;">
                    <a href="/employee/profile" style="color:white; text-decoration:none;">
                        {{latest.employee_name}}
                    </a>
                </h2>

                <p style="color:#9CA3AF; margin-top:5px;">
                    {{latest.role}} | {{latest.team_name}}
                </p>

                <p style="color:#6B7280; margin-top:2px;">
                    {{latest.department}} | {{latest.location}}
                </p>
            </div>

            <div>
            
                {% if role == "EMPLOYEE" %}
                    <a href="/logout" class="logout-btn">Logout</a>
            
                {% elif role == "TEAM_LEAD" %}
                    <a href="/tl/home" class="logout-btn">← Back</a>
            
                {% elif role == "HR_HEAD" %}
                    <a href="/hr/home" class="logout-btn">← Back</a>
            
                {% endif %}
            
            </div>

        </div>
        
        <!-- KPI -->
        <div class="kpi-row">

            <div class="card violet">
                <div>EWBI</div>
                <div class="value">{{latest.ewbi_score}}</div>
            </div>

            <div class="card 
            {% if latest.risk_level == 'LOW' %}green
            {% elif latest.risk_level == 'MEDIUM' %}yellow
            {% else %}red{% endif %}">
                <div>Risk</div>
                <div class="value green">{{latest.risk_level}}</div>
            </div>

            <div class="card 
            {% if latest.risk_level == 'LOW' %}green
            {% elif latest.risk_level == 'MEDIUM' %}yellow
            {% else %}red{% endif %}">
                <div>Trend</div>
                <div class="value 
                {% if latest.trend_delta < 0 %}red{% else %}green{% endif %}">
                {{latest.trend_delta}}
                </div>
            </div>

            <div class="card 
            {% if latest.sustained_flag == 1 %}green
            {% else %}yellow{% endif %}">
                <div>Stability</div>
                <div class="value">
                    {% if latest.sustained_flag == 1 %}
                        ✔
                    {% else %}
                        ⚠
                    {% endif %}
                </div>
            </div>

        </div>

        <!-- EWBI TREND -->
        <div class="section">
            <h3>EWBI Trend</h3>
            <canvas id="ewbiChart"></canvas>
        </div>

        <!-- DIMENSION TREND -->
        <div class="section">
            <h3>Dimension Trends</h3>
            <canvas id="dimChart"></canvas>
        </div>

        <!-- DONUT + BAR GRID -->
        <div class="section" style="display:grid; grid-template-columns:1fr 1fr; gap:20px;">

            <div class="chart-box">
                <h3>Contribution ({{latest.date}})</h3>
                <div class="chart-container">
                    <canvas id="donutChart"></canvas>
                </div>
            </div>

            <div class="chart-box">
                <h3>EWBI Comparison</h3>

                <label style="color:#9CA3AF;">
                    <input type="checkbox"> Same Location Filter
                </label>

                <div class="chart-container">
                    <canvas id="barChart"></canvas>
                </div>
            </div>

        </div>

        <!-- WORK PATTERN -->
        <div class="section">
            <h3>Work Pattern</h3>
            <canvas id="wpChart"></canvas>
        </div>

        <div style="margin-top: 30px; text-align:center;">
            <a href="/employee/insights" class="insights-btn">
                AI Insights →
            </a>
        </div>

    </div>

    <script>

    // EWBI CHART
    new Chart(document.getElementById('ewbiChart'), {
        type: 'line',
        data: {
            labels: {{dates|safe}},
            datasets: [{
                label: 'EWBI',
                data: {{ewbi|safe}},
                borderColor: '#7C3AED',
                tension: 0.3
            }]
        }
    });

    // DIMENSION TREND
    new Chart(document.getElementById('dimChart'), {
        type: 'line',
        data: {
            labels: {{dim_dates|safe}},
            datasets: [
                {label:'Mental', data:{{mental|safe}}, borderColor:'#7C3AED'},
                {label:'Physical', data:{{physical|safe}}, borderColor:'#3B82F6'},
                {label:'Work', data:{{work|safe}}, borderColor:'#F59E0B'},
                {label:'Social', data:{{social|safe}}, borderColor:'#06B6D4'}
            ]
        }
    });
    
    // DONUT
    new Chart(document.getElementById('donutChart'), {
        type: 'doughnut',
        data: {
            labels: ['Mental','Physical','Work','Social'],
            datasets: [{
                data: {{contributions|safe}},
                backgroundColor: ['#7C3AED','#3B82F6','#F59E0B','#06B6D4']
            }]
        },
        options: {                         // 🔥 ADD HERE
            responsive: true,
            maintainAspectRatio: false
        }
    });
    
    // BAR
    new Chart(document.getElementById('barChart'), {
        type: 'bar',
        data: {
            labels: ['Employee','Team','Department'],
            datasets: [{
                data: {{bar|safe}},
                backgroundColor: ['#7C3AED','#10B981','#F59E0B']
            }]
        },
        options: {                         // 🔥 ADD HERE
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            }
        }
    });

    // WORK PATTERN
    new Chart(document.getElementById('wpChart'), {
        type: 'line',
        data: {
            labels: {{wp_dates|safe}},
            datasets: [
                {label:'Meeting', data:{{meeting|safe}}, borderColor:'#EF4444'},
                {label:'After Hours', data:{{after|safe}}, borderColor:'#F59E0B'},
                {label:'Focus', data:{{focus|safe}}, borderColor:'#10B981'},
                {label:'Span', data:{{span|safe}}, borderColor:'#3B82F6'}
            ]
        }
    });

    </script>

    </body>
    </html>
    """

    return render_template_string(
        html,
        role=session.get("role"),
        latest=latest,
        dates=json.dumps(dates),
        ewbi=json.dumps(ewbi),
        wp_dates=json.dumps(wp_dates),
        meeting=json.dumps(meeting),
        after=json.dumps(after),
        focus=json.dumps(focus),
        span=json.dumps(span),
        insights=insights,
        dim_dates=json.dumps(dim_dates),
        mental=json.dumps(mental),
        physical=json.dumps(physical),
        work=json.dumps(work),
        social=json.dumps(social),
        
        contributions=json.dumps(contributions),

        bar=json.dumps([emp_score, team_avg, dept_avg]),
    )