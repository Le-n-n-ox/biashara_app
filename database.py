import sqlite3
import pandas as pd
import os

DB_PATH = "ledger.db"

def init_db():
    os.path.dirname(DB_PATH) and os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            "Transaction Code" TEXT PRIMARY KEY,
            "Date" TEXT,
            "Entity" TEXT,
            "Type" TEXT,
            "Amount (KES)" REAL,
            "Category" TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_transactions_to_db(df: pd.DataFrame):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("transactions", conn, if_exists="append", index=False)
    conn.close()

def load_transactions_from_db() -> pd.DataFrame:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM transactions", conn)
        conn.close()
        return df
    except Exception:
        conn.close()
        return pd.DataFrame(columns=["Transaction Code", "Date", "Entity", "Type", "Amount (KES)", "Category"])

def clear_db():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
