import os

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_TRANSACTION_COLUMNS = (
    "Transaction Code",
    "Date",
    "Entity",
    "Type",
    "Amount (KES)",
    "Category",
    "Channel",
)


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
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                CREATE TABLE IF NOT EXISTS transactions (
                    "Transaction Code" TEXT,
                    "Date" TEXT,
                    "Entity" TEXT,
                    "Type" TEXT,
                    "Amount (KES)" REAL,
                    "Category" TEXT,
                    "Channel" TEXT,
                    user_id INTEGER
                )
                '''
            )
            cursor.execute(
                "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS \"Channel\" TEXT"
            )
            cursor.execute(
                "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id INTEGER"
            )
            cursor.execute(
                '''
                CREATE TABLE IF NOT EXISTS entity_memory (
                    entity TEXT NOT NULL,
                    category TEXT NOT NULL,
                    user_id INTEGER
                )
                '''
            )
            cursor.execute(
                "ALTER TABLE entity_memory ADD COLUMN IF NOT EXISTS user_id INTEGER"
            )

            # Replace legacy single-column keys so the same code/entity can
            # exist independently for different users.
            for table, scoped_columns in (
                ("transactions", {"Transaction Code", "user_id"}),
                ("entity_memory", {"entity", "user_id"}),
            ):
                cursor.execute(
                    """
                    SELECT constraint_row.conname,
                           array_agg(attribute_row.attname ORDER BY key_column.ordinality)
                    FROM pg_constraint AS constraint_row
                    JOIN unnest(constraint_row.conkey) WITH ORDINALITY
                         AS key_column(attnum, ordinality) ON TRUE
                    JOIN pg_attribute AS attribute_row
                         ON attribute_row.attrelid = constraint_row.conrelid
                        AND attribute_row.attnum = key_column.attnum
                    WHERE constraint_row.conrelid = %s::regclass
                      AND constraint_row.contype = 'p'
                    GROUP BY constraint_row.conname
                    """,
                    (table,),
                )
                for constraint_name, columns in cursor.fetchall():
                    if set(columns) != scoped_columns:
                        cursor.execute(
                            sql.SQL("ALTER TABLE {} DROP CONSTRAINT {} CASCADE").format(
                                sql.Identifier(table), sql.Identifier(constraint_name)
                            )
                        )

            cursor.execute(
                '''
                CREATE UNIQUE INDEX IF NOT EXISTS transactions_user_code_idx
                ON transactions (user_id, "Transaction Code")
                WHERE user_id IS NOT NULL
                '''
            )
            cursor.execute(
                '''
                CREATE UNIQUE INDEX IF NOT EXISTS transactions_unscoped_code_idx
                ON transactions ("Transaction Code")
                WHERE user_id IS NULL
                '''
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS entity_memory_user_entity_idx
                ON entity_memory (user_id, entity)
                WHERE user_id IS NOT NULL
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS entity_memory_unscoped_entity_idx
                ON entity_memory (entity)
                WHERE user_id IS NULL
                """
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_transactions_to_db(df: pd.DataFrame, user_id: int | None = None):
    if df.empty:
        return
    init_db()
    transactions = df.copy()
    transactions = transactions[
        [column for column in _TRANSACTION_COLUMNS if column in transactions.columns]
    ]
    transactions["user_id"] = user_id
    columns = transactions.columns.tolist()
    values = [tuple(row) for row in transactions.itertuples(index=False, name=None)]
    query = sql.SQL("INSERT INTO transactions ({}) VALUES %s ON CONFLICT DO NOTHING").format(
        sql.SQL(", ").join(sql.Identifier(column) for column in columns)
    )
    conn = _get_conn()
    try:
        with conn.cursor() as cursor:
            execute_values(cursor, query.as_string(conn), values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_transactions_from_db(user_id: int | None = None) -> pd.DataFrame:
    init_db()
    if user_id is None:
        query = "SELECT * FROM transactions WHERE user_id IS NULL"
        params = None
    else:
        query = "SELECT * FROM transactions WHERE user_id = %s"
        params = (user_id,)
    conn = _get_conn()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df.drop(columns=["user_id"], errors="ignore")
    finally:
        conn.close()


def clear_db(user_id: int):
    init_db()
    conn = _get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_entity_memory(entity: str, category: str, user_id: int | None = None):
    if not entity or not category:
        return
    init_db()
    entity = entity.strip().upper()
    if user_id is None:
        query = """
            INSERT INTO entity_memory (entity, category, user_id) VALUES (%s, %s, NULL)
            ON CONFLICT (entity) WHERE user_id IS NULL
            DO UPDATE SET category = EXCLUDED.category
        """
        params = (entity, category)
    else:
        query = """
            INSERT INTO entity_memory (entity, category, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (user_id, entity) WHERE user_id IS NOT NULL
            DO UPDATE SET category = EXCLUDED.category
        """
        params = (entity, category, user_id)
    conn = _get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_transaction_category(
    transaction_code: str, category: str, user_id: int | None = None
):
    if not transaction_code or not category:
        return
    init_db()
    if user_id is None:
        query = '''
            UPDATE transactions SET "Category" = %s
            WHERE "Transaction Code" = %s AND user_id IS NULL
        '''
        params = (category, transaction_code)
    else:
        query = '''
            UPDATE transactions SET "Category" = %s
            WHERE "Transaction Code" = %s AND user_id = %s
        '''
        params = (category, transaction_code, user_id)
    conn = _get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_entity_memory(user_id: int | None = None) -> dict[str, str]:
    init_db()
    if user_id is None:
        query = "SELECT entity, category FROM entity_memory WHERE user_id IS NULL"
        params = None
    else:
        query = "SELECT entity, category FROM entity_memory WHERE user_id = %s"
        params = (user_id,)
    conn = _get_conn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return {entity: category for entity, category in rows}
    finally:
        conn.close()