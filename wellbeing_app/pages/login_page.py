from flask import request, session, redirect, url_for

from core.db import get_cursor


def login_page():

    error = None

    # -------------------------------
    # HANDLE POST (LOGIN SUBMIT)
    # -------------------------------
    if request.method == "POST":
        employee_id = request.form.get("employee_id")
        password = request.form.get("password")

        try:
            conn, cursor = get_cursor()

            query = """
            SELECT employee_id, password, designation, team_id
            FROM employees
            WHERE employee_id = %s
            """

            cursor.execute(query, (employee_id,))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

            # -------------------------------
            # AUTH CHECK
            # -------------------------------
            if user and user["password"] == password:

                # SESSION SETUP
                session["employee_id"] = user["employee_id"]
                session["role"] = user["designation"]
                session["team_id"] = user["team_id"]

                role = user["designation"]

                # -------------------------------
                # REDIRECT BASED ON ROLE
                # -------------------------------
                if role == "EMPLOYEE":
                    return redirect(url_for("employee_dashboard.dashboard"))

                elif role == "TEAM_LEAD":
                    return redirect(url_for("tl_home_route"))

                elif role == "HR_HEAD":
                    return redirect(url_for("hr_home_route"))

                else:
                    error = "Invalid role assigned"

            else:
                error = "Invalid Employee ID or Password"

        except Exception as e:
            error = "System error. Please try again."
            print("Login Error:", e)

    # -------------------------------
    # HTML (DARK THEME)
    # -------------------------------
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login</title>
        <style>
            body {{
                background-color: #0b0b0b;
                color: white;
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
            }}

            .container {{
                background: #141414;
                padding: 40px;
                border-radius: 12px;
                width: 350px;
                box-shadow: 0 0 20px rgba(90, 15, 46, 0.4);
            }}

            h2 {{
                text-align: center;
                margin-bottom: 25px;
            }}

            input {{
                width: 100%;
                padding: 12px;
                margin: 10px 0;
                border: none;
                border-radius: 6px;
                background: #1f1f1f;
                color: white;
            }}

            input:focus {{
                outline: none;
                border: 1px solid #6a0dad;
            }}

            button {{
                width: 100%;
                padding: 12px;
                margin-top: 15px;
                border: none;
                border-radius: 6px;
                background: linear-gradient(45deg, #5a0f2e, #6a0dad);
                color: white;
                font-weight: bold;
                cursor: pointer;
            }}

            button:hover {{
                opacity: 0.9;
            }}

            .error {{
                color: #ff4d4d;
                text-align: center;
                margin-top: 10px;
            }}
        </style>
    </head>

    <body>
        <div class="container">
            <h2>Employee Login</h2>

            <form method="POST">
                <input type="text" name="employee_id" placeholder="Employee ID" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>

            {"<div class='error'>" + error + "</div>" if error else ""}
        </div>
    </body>
    </html>
    """