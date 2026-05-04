from flask import Flask, session, redirect, url_for
from core.db import get_connection


# -------------------------------
# INIT APP
# -------------------------------
app = Flask(__name__)
app.secret_key = "wellbeing_app_secret_key_v1"


# -------------------------------
# IMPORTS
# -------------------------------
from pages.login_page import login_page
from pages.employee_dashboard import employee_dashboard

from pages.tl_home import tl_home
from pages.team_dashboard import team_dashboard
from pages.hr_home import hr_home
from pages.org_dashboard import org_dashboard
from pages.upload_page import upload_page
from pages.simulation_page import team_simulation
from pages.recommendation_page import team_recommendation
from pages.logout import logout_user


# -------------------------------
# REGISTER DASHBOARD
# -------------------------------
app.register_blueprint(employee_dashboard)
app.register_blueprint(team_dashboard)
app.register_blueprint(org_dashboard)



# -------------------------------
# AUTH HELPERS
# -------------------------------
def is_logged_in():
    return "employee_id" in session


def get_role():
    return session.get("role")


def role_required(allowed_roles):
    def wrapper(func):
        def decorated_function(*args, **kwargs):

            if not is_logged_in():
                return redirect(url_for("login"))

            if get_role() not in allowed_roles:
                return "⛔ Access Denied", 403

            return func(*args, **kwargs)

        decorated_function.__name__ = func.__name__
        return decorated_function

    return wrapper


# -------------------------------
# ROOT
# -------------------------------
@app.route("/")
def root():
    return redirect(url_for("login"))


# -------------------------------
# LOGIN
# -------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    return login_page()

# -------------------------------
# TEAM LEAD HOME
# -------------------------------
@app.route("/tl/home")
@role_required(["TEAM_LEAD"])
def tl_home_route():
    return tl_home()


# -------------------------------
# TEAM DASHBOARD
# -------------------------------
@app.route("/team/dashboard")
@role_required(["TEAM_LEAD", "HR_HEAD"])
def team_dashboard_route():
    return team_dashboard()


# -------------------------------
# HR HOME
# -------------------------------
@app.route("/hr/home")
@role_required(["HR_HEAD"])
def hr_home_route():
    return hr_home()


# -------------------------------
# ORG DASHBOARD
# -------------------------------
@app.route("/org/dashboard")
@role_required(["HR_HEAD"])
def org_dashboard_route():
    return org_dashboard()


# -------------------------------
# UPLOAD
# -------------------------------
@app.route("/upload", methods=["GET", "POST"])
@role_required(["HR_HEAD"])
def upload_route():
    return upload_page()


# -------------------------------
# SIMULATION
# -------------------------------
@app.route("/simulation/<int:team_id>", methods=["GET", "POST"])
def simulation_route(team_id):
    return team_simulation(team_id)


# -------------------------------
# RECOMMENDATIONS
# -------------------------------
@app.route("/recommendation")
@role_required(["TEAM_LEAD", "HR_HEAD"])
def recommendation_route():

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    emp_id = session.get("employee_id")

    # =========================
    # GET TEAM_ID OF USER
    # =========================
    cursor.execute("""
        SELECT team_id
        FROM employees
        WHERE employee_id = %s
    """, (emp_id,))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row or not row["team_id"]:
        return "No team assigned", 400

    team_id = row["team_id"]

    # ✅ CALL FUNCTION WITH TEAM CONTEXT
    return team_recommendation(team_id)


# -------------------------------
# LOGOUT
# -------------------------------
@app.route("/logout")
def logout():
    return logout_user()

# ===============================
# EMPLOYEE PROFILE
# ===============================
@app.route("/employee/profile", methods=["GET", "POST"])
@role_required(["EMPLOYEE", "TEAM_LEAD", "HR_HEAD"])
def employee_profile_route():
    from pages.employee_profile import employee_profile
    return employee_profile()


# ===============================
# EMPLOYEE INSIGHTS
# ===============================
@app.route("/employee/insights")
@role_required(["EMPLOYEE", "TEAM_LEAD", "HR_HEAD"])
def employee_insights_route():
    from pages.employee_insights import employee_insights
    return employee_insights()


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)