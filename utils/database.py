import sqlite3
import pandas as pd
import os

DB_PATH = "data/ledger.db"

def init_db():
    """Initializes the SQLite database and creates the transactions table if it doesn't exist."""
    os.path.dirname(DB_PATH) and os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            amount INTEGER,
            entity TEXT,
            category TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_transactions_to_db(df: pd.DataFrame):
    """Appends a pandas DataFrame of transactions to the SQLite database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    # Append the records to the table, ignoring the dataframe index
    df.to_sql("transactions", conn, if_exists="append", index=False)
    conn.close()

def load_transactions_from_db() -> pd.DataFrame:
    """Loads all saved transactions from the database into a pandas DataFrame."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM transactions", conn)
        
        # FIX: Rename SQLite's lowercase columns to match our App's Title Case expectations
        df.rename(columns={
            "date": "Date", 
            "amount": "Amount", 
            "entity": "Entity", 
            "category": "Category"
        }, inplace=True)
        
        conn.close()
        return df
    except Exception:
        conn.close()
        return pd.DataFrame(columns=["Date", "Amount", "Entity", "Category"])
    
def clear_db():
    """Clears all records from the database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()