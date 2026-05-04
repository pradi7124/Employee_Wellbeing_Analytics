import mysql.connector
from mysql.connector import Error

# -------------------------------
# DB CONFIG
# -------------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "database": "wellbeing_analytics_db"
}

# -------------------------------
# CREATE CONNECTION
# -------------------------------
def get_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)

        if conn.is_connected():
            return conn

    except Error as e:
        print("❌ DB Error:", e)

    return None


# -------------------------------
# GET CURSOR (DICT FORMAT)
# -------------------------------
def get_cursor():
    conn = get_connection()

    if not conn:
        raise Exception("Database connection failed")

    return conn, conn.cursor(dictionary=True)


# -------------------------------
# SAFE EXECUTE (RECOMMENDED)
# -------------------------------
def execute_query(query, params=None, fetch=False):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(query, params or ())

        if fetch:
            result = cursor.fetchall()
            return result

        conn.commit()

    except Error as e:
        print("❌ Query Error:", e)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()