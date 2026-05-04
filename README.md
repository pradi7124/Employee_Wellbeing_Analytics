# 🧠 Wellbeing Analytics Platform

An internal employee wellbeing analytics web application built with **Flask** and **MySQL**. It ingests periodic survey and work-pattern data, computes a proprietary **EWBI (Employee Wellbeing Index)** score, and exposes role-specific dashboards, AI-powered insights, and intervention simulation tools — all in a dark-themed UI.

---

## 📸 Features at a Glance

| Role | Key Capabilities |
|---|---|
| **Employee** | Personal EWBI dashboard, dimension trends, work pattern charts, AI insights |
| **Team Lead** | Team dashboard, intervention simulator, AI strategy recommendations |
| **HR Head** | Everything above + org-wide dashboard, multi-department filtering, CSV upload |

---

## 🏗️ Architecture Overview

```
wellbeing_app/
├── app.py                        # Flask app entry point, route definitions, role guards
├── requirements.txt
├── core/
│   └── db.py                     # MySQL connection helpers
├── automation/
│   └── pipeline_runner.py        # 10-step data ingestion pipeline
├── pages/
│   ├── login_page.py
│   ├── logout.py
│   ├── employee_dashboard.py     # /employee/dashboard
│   ├── employee_insights.py      # /employee/insights  (AI)
│   ├── employee_profile.py       # /employee/profile
│   ├── tl_home.py                # /tl/home
│   ├── team_dashboard.py         # /team/dashboard
│   ├── hr_home.py                # /hr/home
│   ├── org_dashboard.py          # /org/dashboard
│   ├── upload_page.py            # /upload
│   ├── simulation_page.py        # /simulation/<team_id>
│   └── recommendation_page.py   # /recommendation
└── data/
    └── uploads/                  # CSV files land here after upload
```

---

## 📐 EWBI Score Model

The **Employee Wellbeing Index** is a composite 0–100 score across four dimensions, each weighted equally:

```
EWBI = (Mental × 0.25) + (Physical × 0.25) + (Work Pattern × 0.25) + (Social × 0.25)
```

| Dimension | Source questions | What it captures |
|---|---|---|
| **Mental** | Q10–Q15 | Focus, mindset, resilience, cognitive load |
| **Physical** | Q25–Q28 | Energy, ergonomics, screen fatigue |
| **Work Pattern** | Workday span hours | Workload balance, schedule structure |
| **Social** | Q19–Q22 | Psychological safety, communication, peer support |

**Risk levels:** LOW (≥ 70) · MEDIUM (40–69) · HIGH (< 40)

---

## 🗄️ Database Schema (Quick Reference)

| Table | Purpose |
|---|---|
| `employees` | Employee records, roles, team assignment, passwords |
| `teams` | Team metadata, department, manager |
| `options` | Question → answer → numeric value mapping |
| `responses_raw` | Raw per-employee per-question answers |
| `survey_responses` | Aggregated survey metrics per employee per date |
| `work_pattern_metrics` | Meeting hours, focus hours, after-hours, span |
| `dimension_scores` | Computed 0–100 scores per dimension per date |
| `ewbi_scores` | Final EWBI + dimension contributions |
| `risk_levels` | Risk classification, trend delta, sustained flag |
| `team_daily_metrics` | Team-level daily aggregates |
| `org_daily_metrics` | Org-level daily aggregates |

Views used by dashboards: `employee_dashboard_view`, `team_dashboard_view`

---

## ⚙️ Local Setup Guide

### Prerequisites

- Python 3.10+ (tested on 3.14)
- MySQL or MariaDB (tested on MariaDB 10.4)
- [Ollama](https://ollama.com/) with the Mistral model pulled (for AI features)
- Git

---

### 1. Clone the repository

```bash
git clone https://github.com/your-username/wellbeing-app.git
cd wellbeing-app
```

---

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

---

### 3. Install dependencies

```bash
pip install flask mysql-connector-python pandas requests
```

> If you have a `requirements.txt`, run `pip install -r requirements.txt` instead.

---

### 4. Set up the database

#### 4a. Create the database

Log into MySQL/MariaDB:

```bash
mysql -u root -p
```

Then run:

```sql
CREATE DATABASE wellbeing_analytics_db CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
EXIT;
```

#### 4b. Import the SQL file

The repository includes a complete SQL dump (`Database/wellbeing_analytics_db.sql`) with:

- All table and view definitions
- The `options` question-answer mapping table (required for pipeline)
- Sample employee and team records
- 5 months of pre-seeded data (March – July 2026)

Import it:

```bash
mysql -u root -p wellbeing_analytics_db < Database/wellbeing_analytics_db.sql
```

This single command creates every table, every view, and loads all sample data. No additional migrations needed.

---

### 5. Configure database credentials

Open `wellbeing_app/core/db.py` and update if your MySQL credentials differ from the defaults:

```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_password_here",   # add this line if you have a password
    "database": "wellbeing_analytics_db"
}
```

> By default the config has no password field — add `"password": "..."` if your MySQL root requires one.

---

### 6. Set up Ollama (for AI features)

AI Insights and Team Recommendations require a locally running Ollama instance with Mistral.

```bash
# Install Ollama from https://ollama.com/
ollama pull mistral
ollama serve          # starts on http://localhost:11434 by default
```

> If Ollama is not running, AI pages will gracefully fall back to pre-written static text — the rest of the app works fine without it.

---

### 7. Run the app

```bash
cd wellbeing_app
python app.py
```

The app starts at **http://127.0.0.1:5000**

---

## 🔐 Default Login Credentials

Use these to log in from the SQL seed data:

| Role | Employee ID | Password | Home page |
|---|---|---|---|
| HR Head | *(check `employees` table where `designation = 'HR_HEAD'`)* | as seeded | `/hr/home` |
| Team Lead | *(check `designation = 'TEAM_LEAD'`)* | as seeded | `/tl/home` |
| Employee | *(check `designation = 'EMPLOYEE'`)* | as seeded | `/employee/dashboard` |

To look up credentials directly:

```sql
SELECT employee_id, name, designation, password FROM wellbeing_analytics_db.employees LIMIT 20;
```

---

## 📤 Uploading New Survey Data

HR Heads can upload new cycles at `/upload`. Two CSV files are expected:

### Responses CSV (required)

Must contain exactly these 20 columns with text answers:

```
Q1, Q2, Q3, Q4, Q5, Q6,
Q10, Q11, Q12, Q13, Q14, Q15,
Q19, Q20, Q21, Q22,
Q25, Q26, Q27, Q28
```

Each row = one employee. Row order maps to `employee_id` starting at `1001`. Answer text must exactly match the values in the `options` table (case-insensitive).

Example row:

```
Slightly high,Occasionally,Predictable,Moderate,Improve productivity,Controlled,In control,Moderate,Slightly tired,Clarify immediately,Occasionally,Analyze and fix,Often,Comfortable,Mostly clear,Rare,Moderate,Fully refreshed,Comfortable,Minimal
```

### Work Pattern CSV (optional)

Must contain these columns (one row per employee, same row order as responses):

```
employee_id, meeting_hours, meeting_count, after_hours_work_hours, focus_hours, workday_span_hours
```

Example row:

```
1, 2.66, 9, 0.35, 3.31, 8.11
```

> Sample CSVs for all 5 months are included under `data/uploads/` for reference.

The pipeline runs automatically on upload and executes all 10 steps in a single atomic transaction. If any step fails, the entire upload is rolled back.

---

## 🧪 Simulation Engine

The intervention simulator (`/simulation/<team_id>`) uses a deterministic model — no LLM involved. It computes how adjusting four work-pattern levers would change EWBI:

| Lever | Effect |
|---|---|
| +Focus hours | Mental +1.5×, Work +2.0× per hour added |
| −After-hours work | Mental +1.0×, Physical +1.2×, Work +1.5× per hour reduced |
| −Meeting hours | Mental +1.0×, Work +1.8× per hour reduced |
| Workday span change | Physical and Work adjust inversely with span |

All dimension scores are clamped to 0–100. Results are returned as JSON via AJAX (no page reload).

---

## 🤖 AI Features

Both AI pages call Ollama at `http://localhost:11434/api/generate` using the `mistral` model.

**Employee Insights** — generates 4 observation-only sections (no recommendations): Overall Summary, Trend Interpretation, Dimension-Level Observations, Comparative Positioning.

**Team Recommendations** — a single combined prompt produces a JSON object with 4 strategy sections: peer team learning, weakest dimension intervention, work pattern optimization, and a strategic summary. The peer team is selected algorithmically (highest EWBI in same department that outperforms current team).

---


## 🛣️ Route Map

| Route | Method | Role required | Description |
|---|---|---|---|
| `/` | GET | — | Redirects to `/login` |
| `/login` | GET, POST | — | Authentication |
| `/logout` | GET | Any | Clears session |
| `/employee/dashboard` | GET | Any | Personal EWBI dashboard |
| `/employee/insights` | GET | Any | AI-generated insights |
| `/employee/profile` | GET, POST | Any | View / update name & password |
| `/tl/home` | GET | TEAM_LEAD | Team lead home |
| `/team/dashboard` | GET | TEAM_LEAD, HR_HEAD | Team analytics |
| `/hr/home` | GET | HR_HEAD | HR control panel |
| `/org/dashboard` | GET | HR_HEAD | Org-wide analytics |
| `/upload` | GET, POST | HR_HEAD | Upload survey CSVs |
| `/simulation/<team_id>` | GET, POST | TEAM_LEAD, HR_HEAD | Intervention simulator |
| `/recommendation` | GET | TEAM_LEAD, HR_HEAD | AI strategy report |

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | MySQL / MariaDB |
| Data processing | Pandas |
| Charts | Chart.js (CDN) |
| AI / LLM | Ollama — Mistral 7B (local) |
| Frontend | Vanilla HTML/CSS/JS (inline templates) |

---

## 📄 License

MIT — free to use and modify.
