import os
import sqlite3

import pandas as pd

DB_PATH = os.getenv("DB_PATH", "ledger.db")
TRANSACTION_COLUMNS = (
    "Transaction Code",
    "Date",
    "Entity",
    "Type",
    "Amount (KES)",
    "Category",
    "Channel",
)


def _get_conn() -> sqlite3.Connection:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Create tables with composite keys for multi-user support
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS transactions (
            "Transaction Code" TEXT NOT NULL,
            "Date" TEXT,
            "Entity" TEXT,
            "Type" TEXT,
            "Amount (KES)" REAL,
            "Category" TEXT,
            "Channel" TEXT,
            "user_id" INTEGER,
            PRIMARY KEY ("Transaction Code", "user_id")
        )'''
    )
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS entity_memory (
            entity TEXT NOT NULL,
            category TEXT,
            user_id INTEGER,
            PRIMARY KEY (entity, user_id)
        )'''
    )
    conn.commit()

    # PostgreSQL schema inspection for 'transactions'
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='transactions';")
    transaction_columns = {row[0] for row in cursor.fetchall()}
    
    if "Channel" not in transaction_columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN "Channel" TEXT')
        conn.commit()
    if "user_id" not in transaction_columns:
        cursor.execute('ALTER TABLE transactions ADD COLUMN "user_id" INTEGER')
        conn.commit()

    # PostgreSQL schema inspection for 'entity_memory'
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='entity_memory';")
    memory_columns = {row[0] for row in cursor.fetchall()}
    
    if "user_id" not in memory_columns:
        cursor.execute('ALTER TABLE entity_memory ADD COLUMN "user_id" INTEGER')
        conn.commit()

    cursor.close()
    conn.close()

def save_transactions_to_db(df: pd.DataFrame, user_id: int | None = None) -> None:
    if df.empty:
        return
    init_db()
    records = df.copy()
    records["user_id"] = user_id
    columns = [*TRANSACTION_COLUMNS, "user_id"]
    records = records.reindex(columns=columns)
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    with _get_conn() as conn:
        conn.executemany(
            f"INSERT OR IGNORE INTO transactions ({quoted_columns}) VALUES ({placeholders})",
            [tuple(row) for row in records.itertuples(index=False, name=None)],
        )


def load_transactions_from_db(user_id: int | None = None) -> pd.DataFrame:
    init_db()
    with _get_conn() as conn:
        return pd.read_sql_query(
            'SELECT * FROM transactions WHERE "user_id" IS ?',
            conn,
            params=(user_id,),
        ).drop(columns=["user_id"], errors="ignore")


def clear_db(user_id: int | None = None) -> None:
    init_db()
    with _get_conn() as conn:
        conn.execute('DELETE FROM transactions WHERE "user_id" IS ?', (user_id,))
        conn.execute('DELETE FROM entity_memory WHERE "user_id" IS ?', (user_id,))


def update_entity_memory(entity: str, category: str, user_id: int | None = None) -> None:
    if not entity or not category:
        return
    init_db()
    with _get_conn() as conn:
        conn.execute(
            '''INSERT INTO entity_memory (entity, category, user_id) VALUES (?, ?, ?)
               ON CONFLICT(entity, user_id) DO UPDATE SET category = excluded.category''',
            (entity.strip().upper(), category, user_id),
        )


def update_transaction_category(
    transaction_code: str, category: str, user_id: int | None = None
) -> None:
    if not transaction_code or not category:
        return
    init_db()
    with _get_conn() as conn:
        conn.execute(
            'UPDATE transactions SET "Category" = ? WHERE "Transaction Code" = ? AND "user_id" IS ?',
            (category, transaction_code, user_id),
        )


def get_entity_memory(user_id: int | None = None) -> dict[str, str]:
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            'SELECT entity, category FROM entity_memory WHERE "user_id" IS ?',
            (user_id,),
        ).fetchall()
    return {entity: category for entity, category in rows}
