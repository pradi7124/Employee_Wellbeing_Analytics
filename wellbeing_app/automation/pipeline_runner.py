import pandas as pd
from core.db import get_connection

# =========================================================
# CONFIG
# =========================================================
QUESTION_IDS = [
    "Q1","Q2","Q3","Q4","Q5","Q6",
    "Q10","Q11","Q12","Q13","Q14","Q15",
    "Q19","Q20","Q21","Q22",
    "Q25","Q26","Q27","Q28"
]

BATCH_SIZE = 5000
START_EMPLOYEE_ID = 1001


# =========================================================
# LOAD OPTION MAPPING
# =========================================================
def load_option_mapping(cursor):
    cursor.execute("SELECT question_id, option_text, option_value FROM options")

    mapping = {}
    for qid, text, val in cursor.fetchall():
        mapping[(qid.strip(), text.strip().lower())] = val

    return mapping


# =========================================================
# STEP 1: INSERT RAW RESPONSES
# =========================================================
def insert_raw(cursor, csv_path, survey_date):

    df = pd.read_csv(csv_path)

    for q in QUESTION_IDS:
        if q not in df.columns:
            raise Exception(f"Missing column: {q}")

    mapping = load_option_mapping(cursor)

    insert_query = """
    INSERT INTO responses_raw
    (employee_id, question_id, selected_option_value, survey_date)
    VALUES (%s, %s, %s, %s)
    """

    batch = []

    for idx, row in df.iterrows():
        employee_id = START_EMPLOYEE_ID + idx

        for qid in QUESTION_IDS:
            answer = str(row[qid]).strip().lower()
            key = (qid, answer)

            if key not in mapping:
                raise Exception(f"Mapping missing for {key}")

            batch.append((employee_id, qid, mapping[key], survey_date))

    for i in range(0, len(batch), BATCH_SIZE):
        cursor.executemany(insert_query, batch[i:i+BATCH_SIZE])

    return len(batch)


# =========================================================
# STEP 2: INSERT WORK PATTERN
# =========================================================
def insert_workpattern(cursor, csv_path, survey_date):

    if not csv_path:
        return 0

    df = pd.read_csv(csv_path)

    required_cols = [
        "meeting_hours",
        "meeting_count",
        "after_hours_work_hours",
        "focus_hours",
        "workday_span_hours"
    ]

    for col in required_cols:
        if col not in df.columns:
            raise Exception(f"Missing column: {col}")

    insert_query = """
    INSERT INTO work_pattern_metrics
    (employee_id, date, meeting_hours, meeting_count,
     after_hours_work_hours, focus_hours, workday_span_hours)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    """

    batch = []

    for idx, row in df.iterrows():
        employee_id = START_EMPLOYEE_ID + idx

        batch.append((
            employee_id,
            survey_date,
            row.get("meeting_hours"),
            row.get("meeting_count"),
            row.get("after_hours_work_hours"),
            row.get("focus_hours"),
            row.get("workday_span_hours")
        ))

    for i in range(0, len(batch), BATCH_SIZE):
        cursor.executemany(insert_query, batch[i:i+BATCH_SIZE])

    return len(batch)


# =========================================================
# STEP 3: SURVEY RESPONSES
# =========================================================
def build_survey_responses(cursor, survey_date):

    query = """
    INSERT INTO survey_responses
    (employee_id, survey_date, stress_level, burnout_level,
     energy_level, fatigue_level, satisfaction_level)

    SELECT
        employee_id,
        survey_date,

        AVG(CASE WHEN question_id IN ('Q10','Q11','Q12','Q13','Q14','Q15')
            THEN selected_option_value END),

        AVG(CASE WHEN question_id IN ('Q1','Q2','Q3','Q4','Q5','Q6')
            THEN selected_option_value END),

        AVG(CASE WHEN question_id IN ('Q25','Q26','Q27','Q28')
            THEN selected_option_value END),

        AVG(CASE WHEN question_id IN ('Q25','Q26','Q27','Q28')
            THEN selected_option_value END),

        AVG(CASE WHEN question_id IN ('Q19','Q20','Q21','Q22')
            THEN selected_option_value END)

    FROM responses_raw
    WHERE survey_date = %s
    GROUP BY employee_id, survey_date
    """

    cursor.execute(query, (survey_date,))
    return cursor.rowcount


# =========================================================
# MAIN PIPELINE
# =========================================================
def run_pipeline(responses_csv, survey_date, workpattern_csv=None):

    conn = get_connection()
    cursor = conn.cursor()

    try:
        conn.start_transaction()

        # -------------------------------
        # ID CHECK
        # -------------------------------
        cursor.execute(
            "SELECT COUNT(*) FROM responses_raw WHERE survey_date = %s",
            (survey_date,)
        )
        if cursor.fetchone()[0] > 0:
            raise Exception("Data already exists for this date")

        # -------------------------------
        # RAW
        # -------------------------------
        raw_count = insert_raw(cursor, responses_csv, survey_date)

        # -------------------------------
        # WORK PATTERN
        # -------------------------------
        wp_count = insert_workpattern(cursor, workpattern_csv, survey_date)

        # -------------------------------
        # SURVEY RESPONSES
        # -------------------------------
        sr_count = build_survey_responses(cursor, survey_date)

        # =========================================================
        # STEP 4: DIMENSION SCORES (NORMALIZED)
        # =========================================================
        cursor.execute("""
        INSERT INTO dimension_scores
        (employee_id, date, mental_score, physical_score,
         work_pattern_score, social_score, calculation_version)

        SELECT
            sr.employee_id,
            sr.survey_date,

            (sr.stress_level / 5) * 100,
            (sr.burnout_level / 5) * 100,
            (wp.workday_span_hours / 12) * 100,
            (sr.satisfaction_level / 5) * 100,

            'v2'

        FROM survey_responses sr
        LEFT JOIN work_pattern_metrics wp
        ON sr.employee_id = wp.employee_id AND sr.survey_date = wp.date

        WHERE sr.survey_date = %s
        """, (survey_date,))

        # =========================================================
        # STEP 5: EWBI (CONSISTENT)
        # =========================================================
        cursor.execute("""
        INSERT INTO ewbi_scores
        (employee_id, date, ewbi_score,
         mental_contribution, physical_contribution,
         work_pattern_contribution, social_contribution)

        SELECT
            employee_id,
            date,

            (mental_score*0.25 +
             physical_score*0.25 +
             work_pattern_score*0.25 +
             social_score*0.25),

            mental_score*0.25,
            physical_score*0.25,
            work_pattern_score*0.25,
            social_score*0.25

        FROM dimension_scores
        WHERE date = %s
        """, (survey_date,))

                # =========================================================
        # STEP 6: RISK (BASE INSERT)
        # =========================================================
        cursor.execute("""
        INSERT INTO risk_levels
        (employee_id, date, risk_level, trend_delta, sustained_flag)

        SELECT
            employee_id,
            date,
            CASE
                WHEN ewbi_score >= 70 THEN 'LOW'
                WHEN ewbi_score >= 40 THEN 'MEDIUM'
                ELSE 'HIGH'
            END,
            NULL,
            0

        FROM ewbi_scores
        WHERE date = %s
        """, (survey_date,))


        # =========================================================
        # STEP 7: TREND DELTA (INCREMENTAL)
        # =========================================================
        cursor.execute("""
        UPDATE risk_levels rl
        JOIN (
            SELECT 
                employee_id,
                date,
                ewbi_score,
                LAG(ewbi_score) OVER (
                    PARTITION BY employee_id 
                    ORDER BY date
                ) AS prev_ewbi
            FROM ewbi_scores
        ) t
        ON rl.employee_id = t.employee_id AND rl.date = t.date

        SET rl.trend_delta =
            CASE
                WHEN t.prev_ewbi IS NULL THEN NULL
                ELSE t.ewbi_score - t.prev_ewbi
            END
        WHERE rl.date = %s
        """, (survey_date,))


        # =========================================================
        # STEP 8: SUSTAINED FLAG (3-POINT MOMENTUM)
        # =========================================================
        cursor.execute("""
        UPDATE risk_levels rl
        JOIN (
            SELECT 
                employee_id,
                date,
                trend_delta,
                LAG(trend_delta, 1) OVER (PARTITION BY employee_id ORDER BY date) AS t1,
                LAG(trend_delta, 2) OVER (PARTITION BY employee_id ORDER BY date) AS t2
            FROM risk_levels
        ) t
        ON rl.employee_id = t.employee_id AND rl.date = t.date

        SET rl.sustained_flag =
            CASE 
                WHEN t.trend_delta > 0 AND t.t1 > 0 AND t.t2 > 0 THEN 1
                ELSE 0
            END
        WHERE rl.date = %s
        """, (survey_date,))


        # =========================================================
        # STEP 9: TEAM METRICS
        # =========================================================
        cursor.execute("""
        INSERT INTO team_daily_metrics
        (team_id, date, avg_ewbi, avg_mental, avg_physical,
         avg_work_pattern, avg_social, risk_count_high,
         risk_count_medium, cohort_size)

        SELECT
            e.team_id,
            es.date,
            AVG(es.ewbi_score),
            AVG(es.mental_contribution),
            AVG(es.physical_contribution),
            AVG(es.work_pattern_contribution),
            AVG(es.social_contribution),
            SUM(CASE WHEN rl.risk_level='HIGH' THEN 1 ELSE 0 END),
            SUM(CASE WHEN rl.risk_level='MEDIUM' THEN 1 ELSE 0 END),
            COUNT(*)

        FROM ewbi_scores es
        JOIN employees e ON es.employee_id = e.employee_id
        LEFT JOIN risk_levels rl
        ON es.employee_id = rl.employee_id AND es.date = rl.date

        WHERE es.date = %s
        GROUP BY e.team_id, es.date
        """, (survey_date,))


        # =========================================================
        # STEP 10: ORG METRICS
        # =========================================================
        cursor.execute("""
        INSERT INTO org_daily_metrics
        (date, avg_ewbi, avg_mental, avg_physical,
         avg_work_pattern, avg_social,
         total_high_risk, total_medium_risk)

        SELECT
            es.date,
            AVG(es.ewbi_score),
            AVG(es.mental_contribution),
            AVG(es.physical_contribution),
            AVG(es.work_pattern_contribution),
            AVG(es.social_contribution),
            SUM(CASE WHEN rl.risk_level='HIGH' THEN 1 ELSE 0 END),
            SUM(CASE WHEN rl.risk_level='MEDIUM' THEN 1 ELSE 0 END)

        FROM ewbi_scores es
        LEFT JOIN risk_levels rl
        ON es.employee_id = rl.employee_id AND es.date = rl.date

        WHERE es.date = %s
        GROUP BY es.date
        """, (survey_date,))

        conn.commit()

        return {
            "status": "success",
            "raw_inserted": raw_count,
            "workpattern_inserted": wp_count,
            "survey_responses": sr_count
        }

    except Exception as e:
        conn.rollback()
        return {"status": "failed", "error": str(e)}

    finally:
        cursor.close()
        conn.close()