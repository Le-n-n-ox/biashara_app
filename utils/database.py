import sqlite3
import pandas as pd
import os

DB_PATH = "data/ledger.db"

def init_db():
    """Initializes the SQLite database with transactions and memory tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Main ledger table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            amount INTEGER,
            entity TEXT,
            category TEXT
        )
    """)
    
    # Lennox's Feature: Recurring Entity Memory Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_memory (
            entity TEXT PRIMARY KEY,
            category TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_transactions_to_db(df: pd.DataFrame):
    """Appends a pandas DataFrame of transactions to the SQLite database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("transactions", conn, if_exists="append", index=False)
    conn.close()

def load_transactions_from_db() -> pd.DataFrame:
    """Loads all saved transactions from the database into a pandas DataFrame."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM transactions", conn)
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

# --- Lennox's Memory Cache Functions ---

def update_entity_memory(entity: str, category: str):
    """Saves or updates the learned category for a specific entity."""
    if not entity or not category: return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # INSERT OR REPLACE acts as an 'upsert' - creating or updating the row
    cursor.execute(
        "INSERT OR REPLACE INTO entity_memory (entity, category) VALUES (?, ?)", 
        (entity.strip().upper(), category)
    )
    conn.commit()
    conn.close()

def get_entity_memory() -> dict:
    """Returns a dictionary of all learned {Entity: Category} mappings."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT entity, category FROM entity_memory")
    rows = cursor.fetchall()
    conn.close()
    
    return {row[0]: row[1] for row in rows}