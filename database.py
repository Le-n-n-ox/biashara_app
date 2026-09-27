import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    if not DB_URL:
        raise ValueError("DATABASE_URL environment variable is not set in .env")
    return psycopg2.connect(DB_URL)

def init_db():
    """Initializes the PostgreSQL database with transactions and entity memory."""
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            "Transaction Code" TEXT PRIMARY KEY,
            "Date" TEXT,
            "Entity" TEXT,
            "Type" TEXT,
            "Amount (KES)" REAL,
            "Category" TEXT,
            "Channel" TEXT
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_memory (
            entity TEXT PRIMARY KEY,
            category TEXT
        );
    """)
    conn.commit()

    # Migration check for Channel column
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='transactions';")
    existing_columns = [row[0] for row in cursor.fetchall()]
    if "Channel" not in existing_columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN "Channel" TEXT;')
        conn.commit()

    cursor.close()
    conn.close()

def save_transactions_to_db(df: pd.DataFrame):
    if df.empty:
        return
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()
    
    columns = df.columns.tolist()
    values = [tuple(x) for x in df.to_numpy()]
    insert_query = f"""
        INSERT INTO transactions ("{'", "'.join(columns)}") 
        VALUES %s 
        ON CONFLICT ("Transaction Code") DO NOTHING;
    """
    execute_values(cursor, insert_query, values)
    conn.commit()
    cursor.close()
    conn.close()

def load_transactions_from_db() -> pd.DataFrame:
    init_db()
    conn = _get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM transactions", conn)
        conn.close()
        return df
    except Exception:
        conn.close()
        return pd.DataFrame(columns=["Transaction Code", "Date", "Entity", "Type", "Amount (KES)", "Category", "Channel"])

def clear_db():
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions;")
    conn.commit()
    cursor.close()
    conn.close()

def update_entity_memory(entity: str, category: str):
    if not entity or not category:
        return
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO entity_memory (entity, category) VALUES (%s, %s)
        ON CONFLICT (entity) DO UPDATE SET category = EXCLUDED.category;
    """, (entity.strip().upper(), category))
    conn.commit()
    cursor.close()
    conn.close()

def update_transaction_category(transaction_code: str, category: str):
    if not transaction_code or not category:
        return
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE transactions SET "Category" = %s WHERE "Transaction Code" = %s;', (category, transaction_code))
    conn.commit()
    cursor.close()
    conn.close()

def get_entity_memory() -> dict:
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT entity, category FROM entity_memory;")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {entity: category for entity, category in rows}