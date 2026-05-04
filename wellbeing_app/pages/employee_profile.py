from flask import render_template_string, session, redirect, request
from core.db import get_connection


def employee_profile():

    if "employee_id" not in session:
        return redirect("/")

    emp_id = session["employee_id"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ============================================
    # HANDLE FORM SUBMIT
    # ============================================
    message = None

    if request.method == "POST":

        new_name = request.form.get("name")
        new_password = request.form.get("password")

        # ---------------------------
        # UPDATE NAME
        # ---------------------------
        if new_name and new_name.strip() != "":
            cursor.execute("""
            UPDATE employees
            SET name = %s
            WHERE employee_id = %s
            """, (new_name.strip(), emp_id))
            conn.commit()
            message = "Name updated successfully"

        # ---------------------------
        # UPDATE PASSWORD
        # ---------------------------
        if new_password and new_password.strip() != "":
            cursor.execute("""
            UPDATE employees
            SET password = %s
            WHERE employee_id = %s
            """, (new_password.strip(), emp_id))
            conn.commit()

            # 🔥 FORCE LOGOUT
            session.clear()
            cursor.close()
            conn.close()
            return redirect("/login")

    # ============================================
    # FETCH EMPLOYEE DATA
    # ============================================
    cursor.execute("""
    SELECT 
        e.employee_id,
        e.name,
        e.role,
        e.location,
        e.team_id,
        t.team_name,
        t.department
    FROM employees e
    JOIN teams t ON e.team_id = t.team_id
    WHERE e.employee_id = %s
    """, (emp_id,))

    emp = cursor.fetchone()

    cursor.close()
    conn.close()

    # ============================================
    # HTML
    # ============================================

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Employee Profile</title>
        <style>
            body {
                background:#0B0B0F;
                color:white;
                font-family:Arial;
                padding:20px;
            }

            .container {
                max-width:800px;
                margin:auto;
            }

            .header {
                display:flex;
                justify-content:space-between;
                align-items:center;
                margin-bottom:30px;
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

            .card {
                background:#111827;
                padding:25px;
                border-radius:12px;
            }

            .row {
                margin-bottom:15px;
            }

            label {
                display:block;
                color:#9CA3AF;
                margin-bottom:5px;
            }

            input {
                width:100%;
                padding:10px;
                border-radius:8px;
                border:none;
                background:#1F2937;
                color:white;
            }

            .btn {
                margin-top:15px;
                padding:12px 18px;
                border:none;
                border-radius:8px;
                background:#7C3AED;
                color:white;
                font-weight:600;
                cursor:pointer;
            }

            .btn:hover {
                background:#6D28D9;
            }

            .msg {
                margin-top:15px;
                color:#10B981;
            }

        </style>
    </head>
    <body>

    <div class="container">

        <div class="header">
            <h2>Profile</h2>
            <a href="/employee/dashboard" class="back-btn">← Back</a>
        </div>

        <div class="card">

            <!-- DISPLAY -->
            <div class="row"><strong>Name:</strong> {{emp.name}}</div>
            <div class="row"><strong>Employee ID:</strong> {{emp.employee_id}}</div>
            <div class="row"><strong>Role:</strong> {{emp.role}}</div>
            <div class="row"><strong>Team:</strong> {{emp.team_name}}</div>
            <div class="row"><strong>Department:</strong> {{emp.department}}</div>
            <div class="row"><strong>Location:</strong> {{emp.location}}</div>
            <div class="row"><strong>Password:</strong> ********</div>

            <hr style="margin:20px 0; border-color:#374151;">

            <!-- UPDATE FORM -->
            <form method="POST">

                <div class="row">
                    <label>Update Name</label>
                    <input type="text" name="name" placeholder="Enter new name">
                </div>

                <div class="row">
                    <label>Update Password</label>
                    <input type="password" name="password" placeholder="Enter new password">
                </div>

                <button type="submit" class="btn">Update</button>

            </form>

            {% if message %}
                <div class="msg">{{message}}</div>
            {% endif %}

        </div>

    </div>

    </body>
    </html>
    """

    return render_template_string(html, emp=emp, message=message)