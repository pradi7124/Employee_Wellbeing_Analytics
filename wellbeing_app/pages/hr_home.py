from flask import session, redirect, url_for, render_template_string
from core.db import get_connection


def hr_home():

    if "employee_id" not in session:
        return redirect(url_for("login"))

    emp_id = session["employee_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT team_id
        FROM employees
        WHERE employee_id = %s
    """, (emp_id,))

    row = cursor.fetchone()

    if not row:
        return "Team not assigned", 400

    team_id = row["team_id"]

    cursor.close()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>HR Control Panel</title>

        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #0B0B0F;
                color: white;
            }

            .container {
                max-width: 1000px;
                margin: auto;
                padding: 50px 20px;
            }

            h1 {
                text-align: center;
                margin-bottom: 40px;
                font-size: 38px;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
                gap: 25px;
            }

            .card {
                background: #111827;
                border-radius: 14px;
                padding: 35px 20px;
                text-align: center;
                text-decoration: none;
                color: white;
                font-size: 22px;
                font-weight: bold;
                transition: 0.3s ease;
            }

            .card:hover {
                transform: translateY(-6px);
                box-shadow: 0 0 20px rgba(124,58,237,0.45);
                background: linear-gradient(135deg, #111827, #1E1B4B);
            }

            .logout-wrap {
                text-align: center;
                margin-top: 35px;
            }

            .logout-btn {
                display: inline-block;
                background: #7F1D1D;
                color: white;
                text-decoration: none;
                font-size: 18px;
                font-weight: bold;
                padding: 12px 28px;
                border-radius: 10px;
            }
        </style>

    </head>

    <body>

        <div class="container">
            <h1>HR Head Home</h1>

            <div class="grid">

                <a href="/employee/dashboard" class="card">
                    Personal Dashboard
                </a>

                <a href="/team/dashboard" class="card">
                    Team Dashboard
                </a>

                <a href="/simulation/{{team_id}}" class="card">
                    Team Simulation
                </a>

                <a href="/team/recommendation/{{team_id}}" class="card">
                    AI Team Recommendations
                </a>

                <a href="/org/dashboard" class="card">
                    Org Dashboard
                </a>

                <a href="/upload" class="card">
                    Upload Data
                </a>

            </div>

            <div class="logout-wrap">
                <a href="/logout" class="logout-btn">
                    Logout
                </a>
            </div>

        </div>

    </body>
    </html>
    """

    return render_template_string(html, team_id=team_id)