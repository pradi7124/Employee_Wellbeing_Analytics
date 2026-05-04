from flask import render_template_string, session, redirect
from core.db import get_connection
import requests
import json


# =========================================================
# OLLAMA CALL
# =========================================================
def call_ollama(prompt):

    for attempt in range(2):
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 250
                    }
                },
                timeout=120
            )

            return response.json()["response"]

        except Exception as e:
            print("OLLAMA ERROR:", e)

    return ""


# =========================================================
# FEATURE ENGINEERING
# =========================================================
def build_features(cursor, emp_id):

    def safe(val, default=0):
        try:
            return float(val) if val is not None else default
        except:
            return default
    # -------- Latest snapshot --------
    cursor.execute("""
    SELECT *
    FROM employee_dashboard_view
    WHERE employee_id = %s
    ORDER BY date DESC
    LIMIT 1
    """, (emp_id,))
    latest = cursor.fetchone()

    # -------- Trend data --------
    cursor.execute("""
    SELECT date, ewbi_score
    FROM employee_dashboard_view
    WHERE employee_id = %s
    ORDER BY date
    """, (emp_id,))
    trend = cursor.fetchall()

    ewbi_values = [r["ewbi_score"] for r in trend]

    # -------- Simple trend classification --------
    if len(ewbi_values) >= 2:
        delta = ewbi_values[-1] - ewbi_values[0]
        if delta > 2:
            trend_label = "increasing"
        elif delta < -2:
            trend_label = "declining"
        else:
            trend_label = "stable"
    else:
        trend_label = "insufficient data"

    # -------- Comparison --------
    cursor.execute("""
    SELECT 
        (SELECT AVG(ewbi_score) FROM ewbi_scores WHERE date = %s) as org_avg
    """, (latest["date"],))
    org_avg = cursor.fetchone()["org_avg"]

    if latest["ewbi_score"] > org_avg:
        comparison = "above organization average"
    elif latest["ewbi_score"] < org_avg:
        comparison = "below organization average"
    else:
        comparison = "aligned with organization average"

    return {
        "ewbi": safe(latest["ewbi_score"]),
        "risk": latest["risk_level"] or "UNKNOWN",
        "trend_direction": trend_label,
        "trend_delta": safe(latest["trend_delta"]),
        "stability": "sustained" if latest["sustained_flag"] == 1 else "not sustained",
    
        "dimensions": {
            "mental": safe(latest["mental_score"]),
            "physical": safe(latest["physical_score"]),
            "work_pattern": safe(latest["work_pattern_score"]),
            "social": safe(latest["social_score"])
        },
    
        "comparison": comparison or "unknown"
    }


# =========================================================
# PROMPT BUILDER
# =========================================================
def build_prompt(data):

    return f"""
You are an analytics interpreter.

STRICT RULES:
- Do NOT give recommendations
- Do NOT suggest actions
- Do NOT use advisory words like should, improve, try
- Only describe observations and patterns

FORMAT EXACTLY:

### Overall Well-being Summary
(2 sentences)

### Trend Interpretation
(2 sentences)

### Dimension-Level Observations
(2 sentences)

### Comparative Positioning
(2 sentences)

DATA:
EWBI: {data['ewbi']}
Risk: {data['risk']}
Trend Direction: {data['trend_direction']}
Trend Delta: {data['trend_delta']}
Stability: {data['stability']}
Mental: {data['dimensions']['mental']}
Physical: {data['dimensions']['physical']}
Work Pattern: {data['dimensions']['work_pattern']}
Social: {data['dimensions']['social']}
Comparison: {data['comparison']}
"""


# =========================================================
# MAIN PAGE
# =========================================================
def employee_insights():

    if "employee_id" not in session:
        return redirect("/")

    emp_id = session["employee_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # -------- Build features --------
    features = build_features(cursor, emp_id)

    # -------- Prompt --------
    prompt = build_prompt(features)

    # -------- LLM call --------
    raw_output = call_ollama(prompt)

    cursor.close()
    conn.close()

    if not raw_output.strip():
        raw_output = """
    ### Overall Well-being Summary
    The current well-being score indicates a moderate overall state.
    
    ### Trend Interpretation
    Recent trends indicate fluctuation in performance.
    
    ### Dimension-Level Observations
    Dimension scores show uneven contribution.
    
    ### Comparative Positioning
    The employee appears below the organizational average.
    """

    # -------- Basic parsing --------
    sections = raw_output.split("###")

    parsed = {
        "Overall Well-being Summary": "",
        "Trend Interpretation": "",
        "Dimension-Level Observations": "",
        "Comparative Positioning": ""
    }

    for key in parsed.keys():
        if key in raw_output:
            try:
                part = raw_output.split(key)[1]
                parsed[key] = part.split("###")[0].strip()
            except:
                parsed[key] = "No insight generated"
        else:
            parsed[key] = "No insight generated"

    if not raw_output or len(raw_output.strip()) < 50:
        raw_output = """
    ### Overall Well-being Summary
    Data insufficient for detailed interpretation.

    ### Trend Interpretation
    Trend patterns could not be clearly established.

    ### Dimension-Level Observations
    Dimension-level data appears limited.

    ### Comparative Positioning
    Comparison could not be derived reliably.
    """
        
    print("FEATURES:", features)
    print("RAW OUTPUT:", raw_output)        
    
    # =========================================================
    # HTML
    # =========================================================

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Employee Insights</title>
        <style>
            body {
                background:#0B0B0F;
                color:white;
                font-family:Arial;
                padding:20px;
            }

            .container {
                max-width:1000px;
                margin:auto;
            }

            .header {
                display:flex;
                justify-content:space-between;
                align-items:center;
                margin-bottom:25px;
            }

            .back-btn {
                background:#1F2937;
                padding:10px 16px;
                border-radius:8px;
                text-decoration:none;
                color:white;
            }

            .back-btn:hover {
                background:#374151;
            }

            .section {
                background:#111827;
                padding:20px;
                border-radius:12px;
                margin-bottom:20px;
                border-left:4px solid #7C3AED;
            }

            .title {
                font-weight:600;
                margin-bottom:10px;
                font-size:18px;
            }

            .text {
                color:#9CA3AF;
                line-height:1.6;
            }

            .grid {
                display:grid;
                grid-template-columns:1fr 1fr;
                gap:20px;
            }

        </style>
    </head>
    <body>

    <div class="container">

        <div class="header">
            <h2>AI Insights</h2>
            <a href="/employee/dashboard" class="back-btn">← Back</a>
        </div>

        <div class="section">
            <div class="title">Overall Well-being Summary</div>
            <div class="text">{{data["Overall Well-being Summary"]}}</div>
        </div>

        <div class="grid">

            <div class="section">
                <div class="title">Trend Interpretation</div>
                <div class="text">{{data["Trend Interpretation"]}}</div>
            </div>

            <div class="section">
                <div class="title">Comparative Positioning</div>
                <div class="text">{{data["Comparative Positioning"]}}</div>
            </div>

        </div>

        <div class="section">
            <div class="title">Dimension-Level Observations</div>
            <div class="text">{{data["Dimension-Level Observations"]}}</div>
        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(html, data=parsed)