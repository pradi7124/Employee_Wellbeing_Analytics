from flask import render_template_string, session, redirect
from core.db import get_connection
import requests
import json
import re


# =========================================================
# CONFIG
# =========================================================
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "mistral"


# =========================================================
# NORMALIZATION
# =========================================================
def normalize(value, min_v, max_v):
    if max_v - min_v == 0:
        return 0
    return (value - min_v) / (max_v - min_v)


# =========================================================
# SINGLE COMBINED LLM CALL — returns JSON with 4 keys
# =========================================================
def build_combined_prompt(current, peer, weakest_dim, dim_scores, work_flags):

    gap_ewbi   = round((peer["ewbi"]      or 0) - (current["ewbi"]      or 0), 2)
    gap_work   = round((peer["work"]      or 0) - (current["work"]      or 0), 2)
    gap_social = round((peer["social"]    or 0) - (current["social"]    or 0), 2)
    gap_focus  = round((peer["focus"]     or 0) - (current["focus"]     or 0), 2)
    gap_after  = round((current["after_hours"] or 0) - (peer["after_hours"] or 0), 2)

    dim_context = {
        "Mental":   "focus ability, mindset, resilience, cognitive load",
        "Physical": "energy levels, ergonomic comfort, eye strain, fatigue",
        "Work":     "workload balance, meeting overload, schedule control",
        "Social":   "psychological safety, communication, conflict, peer support"
    }
    survey_q = {
        "Mental":   "Q10-Q15 (mindset, focus, resilience)",
        "Physical": "Q25-Q28 (energy, ergonomics, screen fatigue)",
        "Work":     "Q1-Q6 (workload, overtime, meetings, rhythm)",
        "Social":   "Q19-Q22 (support, openness, communication, conflict)"
    }

    flags_str = ", ".join(work_flags) if work_flags else "all metrics within healthy range"

    return f"""You are an organizational wellbeing strategist. Respond ONLY with a valid JSON object and nothing else — no explanation, no markdown, no extra text.

DATA:
Current Team: {current['team_name']} | EWBI: {current['ewbi']} | Risk: {current['risk_level']} | Stability: {current['stability']}%
Dimensions: Mental={dim_scores['Mental']}, Physical={dim_scores['Physical']}, Work={dim_scores['Work']}, Social={dim_scores['Social']}
Work Pattern: Meeting={current['meeting']}h, AfterHours={current['after_hours']}h, Focus={current['focus']}h, Span={current['span']}h

Peer Team: {peer['team_name']} | EWBI: {peer['ewbi']} | Risk: {peer['risk_level']}
Peer gaps vs Current: EWBI+{gap_ewbi}, Work+{gap_work}, Social+{gap_social}, Focus+{gap_focus}h, AfterHours-{gap_after}h

Weakest Dimension: {weakest_dim} ({dim_scores[weakest_dim]}/100) — covers {dim_context[weakest_dim]} — measured by {survey_q[weakest_dim]}
Work Pattern Issues: {flags_str}

TASK: Write 4 strategy sections. Each must be 2-3 sentences, data-driven using the numbers above, specific and actionable.

Respond with exactly this JSON structure:
{{
  "peer": "2-3 sentences: WHY {peer['team_name']} was selected using the score gaps, and HOW to structure the knowledge transfer activity",
  "dimension": "2-3 sentences: WHY {weakest_dim} is weakest using the score, and WHAT specific intervention will improve it",
  "workpattern": "2-3 sentences: WHAT work pattern issue exists with exact hours, WHY it harms wellbeing, HOW to fix it",
  "summary": "2-3 sentences: tie all three interventions together, reference EWBI score and risk level, state expected outcome"
}}"""


def generate_recommendations(prompt):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 250
                }
            },
            timeout=55          # stay under 60s SQL limit
        )
        raw = response.json().get("response", "").strip()

        # Extract JSON — handle cases where model adds extra text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())

    except Exception as e:
        print("LLM ERROR:", e)

    return None


# =========================================================
# FALLBACKS
# =========================================================
FALLBACKS = {
    "peer":        "A peer team within the same department was selected based on superior EWBI and dimension scores. A structured knowledge transfer session such as a joint retrospective is recommended to close the identified gaps.",
    "dimension":   "The team's weakest dimension score reflects patterns in both survey responses and work metrics. A targeted 4-week intervention focused on root-cause behavioral changes is recommended.",
    "workpattern": "Current work pattern metrics show deviations from healthy baselines. Scheduling reforms to protect focus time and reduce after-hours load will directly improve wellbeing scores.",
    "summary":     "This team requires coordinated intervention across peer learning, dimension improvement, and work pattern reform. Addressing all three areas is expected to produce measurable EWBI improvement within 6-8 weeks."
}


# =========================================================
# MAIN ROUTE
# =========================================================
def team_recommendation(team_id):

    if "employee_id" not in session:
        return redirect("/")

    role = session.get("role")
    if role not in ["HR_HEAD", "TEAM_LEAD"]:
        return "Access Denied", 403

    back_url = "/hr/home" if role == "HR_HEAD" else "/tl/home"

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # TEAM INFO
    cursor.execute("SELECT team_name, department FROM teams WHERE team_id = %s", (team_id,))
    team_info = cursor.fetchone()
    if not team_info:
        return "Invalid Team"
    team_name  = team_info["team_name"]
    department = team_info["department"]

    # LATEST DATE
    cursor.execute("SELECT MAX(DATE(date)) as latest FROM ewbi_scores")
    latest_date = cursor.fetchone()["latest"]

    # CURRENT TEAM METRICS
    cursor.execute("""
        SELECT
            ROUND(AVG(es.ewbi_score),2)             as ewbi,
            ROUND(AVG(ds.mental_score)*25,2)        as mental,
            ROUND(AVG(ds.physical_score)*25,2)      as physical,
            ROUND(AVG(ds.work_pattern_score)*25,2)  as work,
            ROUND(AVG(ds.social_score)*25,2)        as social,
            ROUND(AVG(wp.meeting_hours),2)          as meeting,
            ROUND(AVG(wp.after_hours_work_hours),2) as after_hours,
            ROUND(AVG(wp.focus_hours),2)            as focus,
            ROUND(AVG(wp.workday_span_hours),2)     as span
        FROM employees e
        JOIN ewbi_scores es ON e.employee_id = es.employee_id
        LEFT JOIN dimension_scores ds
            ON e.employee_id = ds.employee_id AND DATE(es.date) = DATE(ds.date)
        LEFT JOIN work_pattern_metrics wp
            ON e.employee_id = wp.employee_id AND DATE(es.date) = DATE(wp.date)
        WHERE e.team_id = %s AND DATE(es.date) = %s
    """, (team_id, latest_date))
    base = cursor.fetchone()

    # RISK + STABILITY — single query with conditional aggregation
    cursor.execute("""
        SELECT
            ROUND(SUM(CASE WHEN rl.sustained_flag=1 THEN 1 ELSE 0 END)*100.0/COUNT(*), 1) as stability,
            (SELECT rl2.risk_level FROM risk_levels rl2
             JOIN employees e2 ON rl2.employee_id = e2.employee_id
             WHERE e2.team_id = %s AND DATE(rl2.date) = %s
             GROUP BY rl2.risk_level ORDER BY COUNT(*) DESC LIMIT 1) as risk_level
        FROM risk_levels rl
        JOIN employees e ON rl.employee_id = e.employee_id
        WHERE e.team_id = %s AND DATE(rl.date) = %s
    """, (team_id, latest_date, team_id, latest_date))
    risk_row = cursor.fetchone() or {}
    base["risk_level"] = risk_row.get("risk_level") or "UNKNOWN"
    base["stability"]  = risk_row.get("stability")  or 0
    base["team_name"]  = team_name

    # ALL DEPARTMENT TEAMS — single query
    cursor.execute("""
        SELECT
            t.team_id, t.team_name,
            ROUND(AVG(es.ewbi_score),2)             as ewbi,
            ROUND(AVG(ds.mental_score)*25,2)        as mental,
            ROUND(AVG(ds.physical_score)*25,2)      as physical,
            ROUND(AVG(ds.work_pattern_score)*25,2)  as work,
            ROUND(AVG(ds.social_score)*25,2)        as social,
            ROUND(AVG(wp.meeting_hours),2)          as meeting,
            ROUND(AVG(wp.after_hours_work_hours),2) as after_hours,
            ROUND(AVG(wp.focus_hours),2)            as focus,
            ROUND(AVG(wp.workday_span_hours),2)     as span,
            ROUND(SUM(CASE WHEN rl.sustained_flag=1 THEN 1 ELSE 0 END)*100.0/COUNT(rl.id), 1) as stability,
            (SELECT rl2.risk_level FROM risk_levels rl2
             JOIN employees e3 ON rl2.employee_id = e3.employee_id
             WHERE e3.team_id = t.team_id AND DATE(rl2.date) = %s
             GROUP BY rl2.risk_level ORDER BY COUNT(*) DESC LIMIT 1) as risk_level
        FROM teams t
        JOIN employees e ON t.team_id = e.team_id
        JOIN ewbi_scores es ON e.employee_id = es.employee_id
        LEFT JOIN dimension_scores ds
            ON e.employee_id = ds.employee_id AND DATE(es.date) = DATE(ds.date)
        LEFT JOIN work_pattern_metrics wp
            ON e.employee_id = wp.employee_id AND DATE(es.date) = DATE(wp.date)
        LEFT JOIN risk_levels rl
            ON e.employee_id = rl.employee_id AND DATE(rl.date) = DATE(es.date)
        WHERE t.department = %s AND DATE(es.date) = %s
        GROUP BY t.team_id, t.team_name
    """, (latest_date, department, latest_date))
    dept_teams = cursor.fetchall()

    cursor.close()
    conn.close()

    # PEER SELECTION
    keys = ["ewbi","mental","physical","work","social","meeting","after_hours","focus","span"]
    mins = {k: min((t[k] or 0) for t in dept_teams) for k in keys}
    maxs = {k: max((t[k] or 0) for t in dept_teams) for k in keys}

    better_teams = [t for t in dept_teams
                    if t["team_id"] != team_id and (t["ewbi"] or 0) > (base["ewbi"] or 0)]

    if better_teams:
        best_team = max(better_teams, key=lambda t: t["ewbi"] or 0)
    else:
        best_team = None
        best_score = float("inf")
        for t in dept_teams:
            if t["team_id"] == team_id:
                continue
            score = sum(abs(
                normalize(base[k] or 0, mins[k], maxs[k]) -
                normalize(t[k]    or 0, mins[k], maxs[k])
            ) for k in keys)
            if score < best_score:
                best_score = score
                best_team = t

    if not best_team:
        best_team = {"team_name": "None", "ewbi": 0, "risk_level": "—",
                     "mental":0,"physical":0,"work":0,"social":0,
                     "meeting":0,"after_hours":0,"focus":0,"span":0,"stability":0}

    # WEAKEST DIMENSION
    dim_scores = {
        "Mental":   base["mental"]   or 0,
        "Physical": base["physical"] or 0,
        "Work":     base["work"]     or 0,
        "Social":   base["social"]   or 0,
    }
    weakest_dim = min(dim_scores, key=dim_scores.get)

    # WORK FLAGS
    work_flags = []
    if (base["after_hours"] or 0) > 2:
        work_flags.append(f"after-hours {base['after_hours']}h/day (>2h threshold)")
    if (base["meeting"]     or 0) > 3:
        work_flags.append(f"meetings {base['meeting']}h/day (>3h threshold)")
    if (base["focus"]       or 0) < 4:
        work_flags.append(f"focus only {base['focus']}h/day (<4h target)")
    if (base["span"]        or 0) > 10:
        work_flags.append(f"workday span {base['span']}h (>10h target)")

    # SINGLE LLM CALL
    result = None
    if best_team["team_name"] != "None":
        prompt = build_combined_prompt(base, best_team, weakest_dim, dim_scores, work_flags)
        result = generate_recommendations(prompt)

    peer_text = (result or {}).get("peer")        or FALLBACKS["peer"]
    dim_text  = (result or {}).get("dimension")   or FALLBACKS["dimension"]
    wp_text   = (result or {}).get("workpattern") or FALLBACKS["workpattern"]
    sum_text  = (result or {}).get("summary")     or FALLBACKS["summary"]

    # BADGE DATA
    flag_badges = []
    if (base["after_hours"] or 0) > 2:
        flag_badges.append({"label": "High After-Hours", "color": "#EF4444", "bg": "#EF444418", "value": f"{base['after_hours']} hrs/day"})
    if (base["meeting"]     or 0) > 3:
        flag_badges.append({"label": "Meeting Overload",  "color": "#F59E0B", "bg": "#F59E0B18", "value": f"{base['meeting']} hrs/day"})
    if (base["focus"]       or 0) < 4:
        flag_badges.append({"label": "Low Focus Time",    "color": "#3B82F6", "bg": "#3B82F618", "value": f"{base['focus']} hrs/day"})
    if (base["span"]        or 0) > 10:
        flag_badges.append({"label": "Long Workday",      "color": "#8B5CF6", "bg": "#8B5CF618", "value": f"{base['span']} hrs"})

    dim_list = [
        {"name": name, "score": score, "pct": min(score, 100), "is_weakest": name == weakest_dim}
        for name, score in dim_scores.items()
    ]

    # ============================
    # HTML
    # ============================
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Team Recommendation</title>
        <style>
            * { box-sizing: border-box; }
            body { background:#0B0B0F; color:white; font-family:Arial,sans-serif; padding:24px; margin:0; }
            .container { max-width:1060px; margin:auto; }
            .header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:28px; }
            .header h2 { margin:0 0 4px; font-size:22px; }
            .header p  { margin:0; color:#9CA3AF; font-size:14px; }
            .back-btn  { background:#1F2937; padding:10px 18px; border-radius:8px; text-decoration:none; color:white; font-size:14px; white-space:nowrap; }
            .kpi-strip { display:grid; grid-template-columns:repeat(5,1fr); gap:14px; margin-bottom:28px; }
            .kpi { background:#111827; border-radius:10px; padding:14px 16px; border-left:4px solid #7C3AED; }
            .kpi .label { font-size:11px; color:#9CA3AF; margin-bottom:6px; text-transform:uppercase; letter-spacing:.5px; }
            .kpi .val   { font-size:22px; font-weight:700; }
            .kpi.green  { border-color:#10B981; }
            .kpi.yellow { border-color:#F59E0B; }
            .kpi.red    { border-color:#EF4444; }
            .card { background:#111827; border-radius:12px; padding:22px 24px; margin-bottom:20px; border-left:4px solid #7C3AED; }
            .card.peer-card { border-color:#10B981; }
            .card.dim-card  { border-color:#3B82F6; }
            .card.wp-card   { border-color:#F59E0B; }
            .card.sum-card  { border-color:#7C3AED; }
            .card-title    { font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:.8px; margin-bottom:6px; }
            .card-subtitle { font-size:11px; color:#6B7280; margin-bottom:14px; }
            .card-text     { color:#D1D5DB; line-height:1.75; font-size:14px; }
            .peer-badge { display:inline-flex; align-items:center; gap:8px; background:#0D2B1F; border:1px solid #10B981; border-radius:8px; padding:8px 14px; margin-bottom:14px; font-size:13px; }
            .peer-badge .dot { width:8px; height:8px; border-radius:50%; background:#10B981; }
            .dim-bars { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px; }
            .dim-bar-row { display:flex; align-items:center; gap:10px; }
            .dim-bar-row .dname { font-size:12px; color:#9CA3AF; width:60px; }
            .dim-bar-wrap { flex:1; background:#1F2937; border-radius:4px; height:8px; }
            .dim-bar-fill { height:8px; border-radius:4px; }
            .dim-bar-row .dnum { font-size:12px; color:#9CA3AF; width:36px; text-align:right; }
            .flags { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
            .flag-badge { border-radius:6px; padding:5px 12px; font-size:12px; font-weight:600; border:1px solid; }
            .two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
        </style>
    </head>
    <body>
    <div class="container">

        <div class="header">
            <div>
                <h2>{{team_name}}</h2>
                <p>{{department}} &middot; Strategy Report &middot; As of {{latest_date}}</p>
            </div>
            <a href="{{back_url}}" class="back-btn">&#8592; Back</a>
        </div>

        <div class="kpi-strip">
            <div class="kpi">
                <div class="label">EWBI Score</div>
                <div class="val">{{base_ewbi}}</div>
            </div>
            <div class="kpi {% if risk == 'LOW' %}green{% elif risk == 'MEDIUM' %}yellow{% else %}red{% endif %}">
                <div class="label">Risk Level</div>
                <div class="val">{{risk}}</div>
            </div>
            <div class="kpi">
                <div class="label">Stability</div>
                <div class="val">{{stability}}%</div>
            </div>
            <div class="kpi">
                <div class="label">Weakest Dim.</div>
                <div class="val" style="font-size:16px;padding-top:4px;">{{weakest_dim}}</div>
            </div>
            <div class="kpi">
                <div class="label">Peer Team</div>
                <div class="val" style="font-size:13px;padding-top:4px;">{{peer_name}}</div>
            </div>
        </div>

        <div class="card peer-card">
            <div class="card-title" style="color:#10B981;">&#9312; Peer Learning Recommendation</div>
            <div class="card-subtitle">Recommended team for knowledge transfer within {{department}}</div>
            {% if peer_name != 'None' %}
            <div class="peer-badge">
                <span class="dot"></span>
                <span>{{peer_name}}</span>
                <span style="color:#9CA3AF;">&middot;</span>
                <span style="color:#10B981;">EWBI {{peer_ewbi}}</span>
                <span style="color:#9CA3AF;">&middot;</span>
                <span style="color:#9CA3AF;">{{peer_risk}} Risk</span>
            </div>
            {% endif %}
            <div class="card-text">{{peer_text}}</div>
        </div>

        <div class="two-col">
            <div class="card dim-card">
                <div class="card-title" style="color:#3B82F6;">&#9313; Dimension Improvement Strategy</div>
                <div class="card-subtitle">Weakest dimension: {{weakest_dim}} ({{weakest_score}} / 100)</div>
                <div class="dim-bars">
                    {% for d in dim_list %}
                    <div class="dim-bar-row">
                        <span class="dname">{{d.name}}</span>
                        <div class="dim-bar-wrap">
                            <div class="dim-bar-fill"
                                style="width:{{d.pct}}%;background:{% if d.is_weakest %}#EF4444{% else %}#3B82F6{% endif %};"></div>
                        </div>
                        <span class="dnum">{{d.score}}</span>
                    </div>
                    {% endfor %}
                </div>
                <div class="card-text">{{dim_text}}</div>
            </div>

            <div class="card wp-card">
                <div class="card-title" style="color:#F59E0B;">&#9314; Work Pattern Optimization</div>
                <div class="card-subtitle">Detected issues based on current metrics</div>
                {% if work_flags %}
                <div class="flags">
                    {% for f in work_flags %}
                    <span class="flag-badge" style="color:{{f.color}};border-color:{{f.color}};background:{{f.bg}};">
                        &#9888; {{f.label}} &middot; {{f.value}}
                    </span>
                    {% endfor %}
                </div>
                {% else %}
                <div style="font-size:12px;color:#10B981;margin-bottom:14px;">&#10004; Work pattern within healthy range</div>
                {% endif %}
                <div class="card-text">{{wp_text}}</div>
            </div>
        </div>

        <div class="card sum-card">
            <div class="card-title" style="color:#A78BFA;">&#9315; Strategic Summary</div>
            <div class="card-subtitle">Consolidated intervention direction for {{team_name}}</div>
            <div class="card-text">{{sum_text}}</div>
        </div>

    </div>
    </body>
    </html>
    """

    return render_template_string(html,
        team_name     = team_name,
        department    = department,
        latest_date   = latest_date,
        back_url      = back_url,
        base_ewbi     = base["ewbi"]     or 0,
        risk          = base["risk_level"],
        stability     = base["stability"],
        weakest_dim   = weakest_dim,
        weakest_score = dim_scores[weakest_dim],
        peer_name     = best_team["team_name"],
        peer_ewbi     = best_team["ewbi"]  or "—",
        peer_risk     = best_team.get("risk_level", "—"),
        dim_list      = dim_list,
        work_flags    = flag_badges,
        peer_text     = peer_text,
        dim_text      = dim_text,
        wp_text       = wp_text,
        sum_text      = sum_text,
    )