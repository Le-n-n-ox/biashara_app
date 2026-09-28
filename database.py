"""
PostgreSQL storage for the ledger and the per-entity category memory.

The connection string comes from DATABASE_URL (environment / .env) and falls
back to Streamlit secrets, the same way utils/auth.py does, so one file works
locally, on Streamlit Cloud and on the FastAPI host.

Ownership: every row carries a user_id. Data that isn't tied to a login
(WhatsApp bot, Daraja callbacks, SMS forwarder) is stored under
UNASSIGNED_USER_ID, so calling any function with user_id=None keeps working.
"""
import os
import threading
from contextlib import contextmanager

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

TRANSACTION_COLUMNS = (
    "Transaction Code",
    "Date",
    "Entity",
    "Type",
    "Amount (KES)",
    "Category",
    "Channel",
)

# Postgres primary-key columns can't be NULL (SQLite let that slide), so "no
# account" is stored as 0. Real users come from a SERIAL and start at 1.
UNASSIGNED_USER_ID = 0

_SCHEMA_LOCK_ID = 726401  # arbitrary constant for pg_advisory_xact_lock
_schema_ready = False
_schema_guard = threading.Lock()


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st  # imported lazily: the FastAPI side never needs it

        return st.secrets["DATABASE_URL"]
    except Exception:
        raise ValueError(
            "DATABASE_URL is not set (checked environment variables and Streamlit secrets)"
        ) from None


@contextmanager
def _connection():
    """Commit on success, roll back on error, always close. A failed query can
    therefore never leave a connection stuck in an aborted transaction."""
    conn = psycopg2.connect(_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _uid(user_id: int | None) -> int:
    return UNASSIGNED_USER_ID if user_id is None else int(user_id)


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def _ensure_user_scoped_pk(cur, table: str, pk_columns: str) -> None:
    """Older versions of these tables keyed on the natural key alone, but
    ON CONFLICT (key, user_id) needs a matching unique constraint. Swap the
    primary key over if it doesn't already include user_id."""
    cur.execute(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND contype = 'p'",
        (table,),
    )
    row = cur.fetchone()
    if row and "user_id" in row[1]:
        return
    if row:
        cur.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                sql.Identifier(table), sql.Identifier(row[0])
            )
        )
    cur.execute(
        sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(
            sql.Identifier(table), sql.SQL(pk_columns)
        )
    )


def init_db() -> None:
    """Create or upgrade the tables. Runs once per process; every later call
    returns immediately (all public functions call this, and Streamlit re-runs
    the whole script on every click)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_guard:
        if _schema_ready:
            return
        with _connection() as conn, conn.cursor() as cur:
            # Serialise startup across processes (Streamlit and FastAPI can boot together).
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))

            cur.execute(
                """CREATE TABLE IF NOT EXISTS transactions (
                    "Transaction Code" TEXT NOT NULL,
                    "Date" TEXT,
                    "Entity" TEXT,
                    "Type" TEXT,
                    "Amount (KES)" DOUBLE PRECISION,
                    "Category" TEXT,
                    "Channel" TEXT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    row_id BIGSERIAL,
                    PRIMARY KEY ("Transaction Code", user_id)
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS entity_memory (
                    entity TEXT NOT NULL,
                    category TEXT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (entity, user_id)
                )"""
            )

            # Upgrade tables created by earlier versions (all no-ops on a fresh DB).
            cur.execute('ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "Channel" TEXT')
            cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id INTEGER")
            cur.execute("ALTER TABLE entity_memory ADD COLUMN IF NOT EXISTS user_id INTEGER")
            for table in ("transactions", "entity_memory"):
                cur.execute(f"UPDATE {table} SET user_id = 0 WHERE user_id IS NULL")
                cur.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET DEFAULT 0")
                cur.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")
            if not _column_exists(cur, "transactions", "row_id"):
                # Insertion order: Postgres has no implicit row order, and "last N
                # transactions" needs one.
                cur.execute("ALTER TABLE transactions ADD COLUMN row_id BIGSERIAL")

            _ensure_user_scoped_pk(cur, "transactions", '"Transaction Code", user_id')
            _ensure_user_scoped_pk(cur, "entity_memory", "entity, user_id")
        _schema_ready = True


def save_transactions_to_db(df: pd.DataFrame, user_id: int | None = None) -> None:
    if df.empty:
        return
    init_db()

    records = df.reindex(columns=list(TRANSACTION_COLUMNS))
    records["Amount (KES)"] = pd.to_numeric(records["Amount (KES)"], errors="coerce")
    uid = _uid(user_id)
    # NaN would be sent as a float and rejected by TEXT columns; store NULL instead.
    values = [
        tuple(None if pd.isna(v) else v for v in row) + (uid,)
        for row in records.itertuples(index=False, name=None)
    ]

    quoted = ", ".join(f'"{c}"' for c in (*TRANSACTION_COLUMNS, "user_id"))
    query = (
        f"INSERT INTO transactions ({quoted}) VALUES %s "
        'ON CONFLICT ("Transaction Code", user_id) DO NOTHING'
    )
    with _connection() as conn, conn.cursor() as cur:
        execute_values(cur, query, values)


def load_transactions_from_db(user_id: int | None = None) -> pd.DataFrame:
    init_db()
    quoted = ", ".join(f'"{c}"' for c in TRANSACTION_COLUMNS)
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {quoted} FROM transactions WHERE user_id = %s ORDER BY row_id",
            (_uid(user_id),),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=list(TRANSACTION_COLUMNS))


def clear_db(user_id: int | None = None) -> None:
    init_db()
    uid = _uid(user_id)
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM transactions WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM entity_memory WHERE user_id = %s", (uid,))


def update_entity_memory(entity: str, category: str, user_id: int | None = None) -> None:
    if not entity or not category:
        return
    init_db()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO entity_memory (entity, category, user_id) VALUES (%s, %s, %s)
               ON CONFLICT (entity, user_id) DO UPDATE SET category = EXCLUDED.category""",
            (entity.strip().upper(), category, _uid(user_id)),
        )


def update_transaction_category(
    transaction_code: str, category: str, user_id: int | None = None
) -> None:
    if not transaction_code or not category:
        return
    init_db()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            'UPDATE transactions SET "Category" = %s WHERE "Transaction Code" = %s AND user_id = %s',
            (category, transaction_code, _uid(user_id)),
        )


def get_entity_memory(user_id: int | None = None) -> dict[str, str]:
    init_db()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT entity, category FROM entity_memory WHERE user_id = %s",
            (_uid(user_id),),
        )
        rows = cur.fetchall()
    return {entity: category for entity, category in rows}