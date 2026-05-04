from flask import request, session, redirect, url_for
import os
from datetime import datetime

from automation.pipeline_runner import run_pipeline

UPLOAD_FOLDER = "data/uploads"


def upload_page():

    # -------------------------------
    # AUTH CHECK
    # -------------------------------
    if "employee_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "HR_HEAD":
        return "⛔ Access Denied", 403

    message = ""

    # -------------------------------
    # HANDLE UPLOAD
    # -------------------------------
    if request.method == "POST":

        try:
            survey_date = request.form.get("survey_date")

            if not survey_date:
                raise Exception("Survey date is required")

            # validate date format
            try:
                datetime.strptime(survey_date, "%Y-%m-%d")
            except:
                raise Exception("Invalid date format (YYYY-MM-DD)")

            responses_file = request.files.get("responses_file")
            workpattern_file = request.files.get("workpattern_file")

            if not responses_file:
                raise Exception("Responses CSV is required")

            # -------------------------------
            # SAVE FILES
            # -------------------------------
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            responses_path = os.path.join(
                UPLOAD_FOLDER, f"responses_{survey_date}.csv"
            )
            responses_file.save(responses_path)

            workpattern_path = None
            if workpattern_file and workpattern_file.filename:
                workpattern_path = os.path.join(
                    UPLOAD_FOLDER, f"workpattern_{survey_date}.csv"
                )
                workpattern_file.save(workpattern_path)

            # -------------------------------
            # RUN PIPELINE
            # -------------------------------
            result = run_pipeline(
                responses_csv=responses_path,
                survey_date=survey_date,
                workpattern_csv=workpattern_path
            )

            if result["status"] == "success":
                message = f"""
                ✅ Upload Successful<br>
                Raw Inserted: {result['raw_inserted']}<br>
                Workpattern Inserted: {result['workpattern_inserted']}<br>
                Survey Responses: {result['survey_responses']}
                """
            else:
                message = f"❌ Failed: {result.get('message') or result.get('error')}"

        except Exception as e:
            message = f"❌ Error: {str(e)}"

    # -------------------------------
    # HTML (DARK THEME)
    # -------------------------------
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Upload Data</title>

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
                width: 400px;
                box-shadow: 0 0 20px rgba(106, 13, 173, 0.4);
            }}

            h2 {{
                text-align: center;
                margin-bottom: 25px;
            }}

            input {{
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                background: #1f1f1f;
                border: none;
                color: white;
                border-radius: 6px;
            }}

            button {{
                width: 100%;
                padding: 12px;
                margin-top: 15px;
                border: none;
                border-radius: 6px;
                background: #1f1f1f;
                color: white;
                cursor: pointer;
                transition: 0.3s;
            }}

            button:hover {{
                border-color: #6a0dad;
                box-shadow: 0 0 10px rgba(106, 13, 173, 0.6);
            }}

            .msg {{
                margin-top: 15px;
                text-align: center;
                font-size: 14px;
            }}

            a {{
                display: block;
                margin-top: 20px;
                text-align: center;
                color: #aaa;
            }}

            a:hover {{
                color: white;
            }}
        </style>
    </head>

    <body>

        <div class="container">
            <h2>Upload Survey Data</h2>

            <form method="POST" enctype="multipart/form-data">

                <label>Survey Date</label>
                <input type="date" name="survey_date" required>

                <label>Responses CSV</label>
                <input type="file" name="responses_file" accept=".csv" required>

                <label>Work Pattern CSV (Optional)</label>
                <input type="file" name="workpattern_file" accept=".csv">

                <button type="submit">Upload & Run Pipeline</button>
            </form>

            <div class="msg">{message}</div>

            <a href="/hr/home">← Back to HR Home</a>
        </div>

    </body>
    </html>
    """