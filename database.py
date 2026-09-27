import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

def _get_conn():
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        try:
            db_url = st.secrets["DATABASE_URL"]
        except Exception:
            pass
            
    if not db_url:
        raise ValueError("DATABASE_URL environment variable or secret is not set")
        
    return psycopg2.connect(db_url)

def init_db():
    conn = _get_conn()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            "Transaction Code" TEXT,
            "Date" TEXT,
            "Entity" TEXT,
            "Type" TEXT,
            "Amount (KES)" REAL,
            "Category" TEXT,

            "Channel" TEXT
        );

            "Channel" TEXT,
            "user_id" INTEGER,
            PRIMARY KEY ("Transaction Code", "user_id")
        )

    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_memory (

            entity TEXT PRIMARY KEY,
            category TEXT
        );
    """)
    conn.commit()

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

            entity TEXT,
            category TEXT,
            user_id INTEGER,
            PRIMARY KEY (entity, user_id)
        )
    """)
    conn.commit()

    # Migration: a ledger.db created before this feature won't have the
    # Channel/user_id columns yet. Add them in place so existing data isn't lost.
    tx_columns = [row[1] for row in cursor.execute('PRAGMA table_info(transactions)').fetchall()]
    if "Channel" not in tx_columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN "Channel" TEXT')
    if "user_id" not in tx_columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN "user_id" INTEGER')

    mem_columns = [row[1] for row in cursor.execute('PRAGMA table_info(entity_memory)').fetchall()]
    if "user_id" not in mem_columns:
        cursor.execute('ALTER TABLE entity_memory ADD COLUMN "user_id" INTEGER')

    conn.commit()
    conn.close()


def save_transactions_to_db(df: pd.DataFrame, user_id: int):
    init_db()
    df = df.copy()
    df["user_id"] = user_id
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("transactions", conn, if_exists="append", index=False)

    conn.close()


def load_transactions_from_db(user_id: int) -> pd.DataFrame:
    init_db()
    conn = _get_conn()
    try:

        df = pd.read_sql_query("SELECT * FROM transactions", conn)

        df = pd.read_sql(
            'SELECT * FROM transactions WHERE "user_id" = ?', conn, params=(user_id,)
        )

        conn.close()
        return df.drop(columns=["user_id"], errors="ignore")
    except Exception:
        conn.close()
        return pd.DataFrame(columns=["Transaction Code", "Date", "Entity", "Type", "Amount (KES)", "Category", "Channel"])


def clear_db(user_id: int):
    init_db()
    conn = _get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM transactions;")

    cursor.execute('DELETE FROM transactions WHERE "user_id" = ?', (user_id,))

    conn.commit()
    cursor.close()
    conn.close()


def update_entity_memory(entity: str, category: str):


def update_entity_memory(entity: str, category: str, user_id: int):
    """Save or update the learned category for an entity, scoped to one user's business."""

    if not entity or not category:
        return
    init_db()

    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO entity_memory (entity, category) VALUES (%s, %s)
        ON CONFLICT (entity) DO UPDATE SET category = EXCLUDED.category;
    """, (entity.strip().upper(), category))

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO entity_memory (entity, category, user_id) VALUES (?, ?, ?)",
        (entity.strip().upper(), category, user_id),
    )

    conn.commit()
    cursor.close()
    conn.close()


def update_transaction_category(transaction_code: str, category: str):


def update_transaction_category(transaction_code: str, category: str, user_id: int):
    """Update the Category of an already-saved transaction row, e.g. after
    a person answers a WhatsApp clarification question about it."""

    if not transaction_code or not category:
        return
    init_db()

    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE transactions SET "Category" = %s WHERE "Transaction Code" = %s;', (category, transaction_code))

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'UPDATE transactions SET "Category" = ? WHERE "Transaction Code" = ? AND "user_id" = ?',
        (category, transaction_code, user_id),
    )

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


def get_entity_memory(user_id: int) -> dict:
    """Return learned entity-to-category mappings for one user's business."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT entity, category FROM entity_memory WHERE user_id = ?", (user_id,)
    ).fetchall()

    conn.close()
    return {entity: category for entity, category in rows}