import sqlite3
import pandas as pd
import os

DB_PATH = "ledger.db"

def init_db():
    """Initializes the SQLite database with transactions and entity memory."""
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            "Transaction Code" TEXT PRIMARY KEY,
            "Date" TEXT,
            "Entity" TEXT,
            "Type" TEXT,
            "Amount (KES)" REAL,
            "Category" TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_memory (
            entity TEXT PRIMARY KEY,
            category TEXT
        )
    """)
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

def update_entity_memory(entity: str, category: str):
    """Save or update the learned category for an entity."""
    if not entity or not category:
        return

    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO entity_memory (entity, category) VALUES (?, ?)",
        (entity.strip().upper(), category),
    )
    conn.commit()
    conn.close()

def get_entity_memory() -> dict:
    """Return learned entity-to-category mappings."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT entity, category FROM entity_memory").fetchall()
    conn.close()
    return {entity: category for entity, category in rows}
