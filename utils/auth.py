"""
Self-contained auth module: user registration + login.
Creates its own `users` table in the same SQLite file your
ledger uses, so it doesn't touch existing ledger schema/logic.
"""
import sqlite3
import hashlib
import hmac
import os
import re
import streamlit as st

DB_PATH = os.getenv("DB_PATH", "biashara.db")  # adjust to match database.py's actual path


def _get_conn():
    return sqlite3.connect(DB_PATH)


def init_auth_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL UNIQUE,
                account_type TEXT NOT NULL,      -- 'Till' or 'Paybill'
                account_number TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Automatic schema migration for existing user tables
        cursor = conn.cursor()
        existing_columns = [row[1] for row in cursor.execute('PRAGMA table_info(users)').fetchall()]

        columns_to_add = {
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "account_type": "TEXT DEFAULT ''",
            "account_number": "TEXT DEFAULT ''",
            "password_hash": "TEXT DEFAULT ''",
            "salt": "TEXT DEFAULT ''"
        }

        for col_name, col_type in columns_to_add.items():
            if col_name not in existing_columns:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {col_name} {col_type}')

        conn.commit()

# ---------- Password hashing (PBKDF2, no extra dependency) ----------
def _hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hashed.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    salt_bytes = bytes.fromhex(stored_salt)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 100_000)
    return hmac.compare_digest(hashed.hex(), stored_hash)


# ---------- Validation ----------
def _clean_phone(phone: str) -> str:
    """Normalizes Kenyan phone numbers to 2547XXXXXXXX / 2541XXXXXXXX format."""
    digits = re.sub(r"\D", "", phone.strip())
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") or digits.startswith("1"):
        if len(digits) == 9:
            digits = "254" + digits
    return digits


def _is_valid_phone(phone: str) -> bool:
    return bool(re.match(r"^254[71]\d{8}$", phone))


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


# ---------- Core operations ----------
def register_user(name: str, email: str, phone: str, account_type: str,
                   account_number: str, password: str) -> tuple[bool, str]:
    name = name.strip()
    email = email.strip().lower()
    phone = _clean_phone(phone)
    account_number = account_number.strip()

    if not name or len(name) < 2:
        return False, "Please enter your full name."
    if not _is_valid_email(email):
        return False, "Enter a valid email address."
    if not _is_valid_phone(phone):
        return False, "Enter a valid Safaricom number (e.g. 0712345678)."
    if account_type not in ("Till", "Paybill"):
        return False, "Select whether this is a Till or Paybill number."
    if not account_number or not account_number.isdigit():
        return False, f"{account_type} number should contain digits only."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    password_hash, salt = _hash_password(password)

    try:
        with _get_conn() as conn:
            conn.execute(
                """INSERT INTO users (name, email, phone, account_type, account_number, password_hash, salt)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, email, phone, account_type, account_number, password_hash, salt),
            )
            conn.commit()
        return True, "Account created. You can now log in."
    except sqlite3.IntegrityError as e:
        if "email" in str(e):
            return False, "This email is already registered."
        return False, "This phone number is already registered."


def authenticate_user(email: str, password: str) -> tuple[bool, str, dict | None]:
    email = email.strip().lower()
    with _get_conn() as conn:
        row = conn.execute(
            """SELECT id, name, email, phone, account_type, account_number, password_hash, salt
               FROM users WHERE email = ?""",
            (email,),
        ).fetchone()

    if not row:
        return False, "No account found with that email.", None

    user_id, name, email, phone, account_type, account_number, password_hash, salt = row
    if not _verify_password(password, password_hash, salt):
        return False, "Incorrect password.", None

    return True, "Login successful.", {
        "id": user_id, "name": name, "email": email, "phone": phone,
        "account_type": account_type, "account_number": account_number,
    }


# ---------- Streamlit UI ----------
def render_auth_gate():
    """Call this at the top of app.py. Returns True once logged in
    (and stops the script for unauthenticated users)."""
    init_auth_db()

    if st.session_state.get("user"):
        return True

    st.title("Biashara Bookkeeper")
    st.caption("Log in or register to access your ledger.")

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@business.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", type="primary", use_container_width=True)

        if submitted:
            ok, message, user = authenticate_user(email, password)
            if ok:
                st.session_state.user = user
                st.rerun()
            else:
                st.error(message)

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email", placeholder="you@business.com")
            phone = st.text_input("Phone Number", placeholder="0712345678",
                                   help="This links your business account to your M-Pesa number.")
            account_type = st.selectbox("Account Type", ["Till", "Paybill"])
            account_number = st.text_input(f"{account_type} Number", placeholder="e.g. 174379")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)

        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match.")
            else:
                ok, message = register_user(name, email, phone, account_type, account_number, password)
                if ok:
                    st.success(message)
                    cleaned_phone = _clean_phone(phone)
                    from utils.notifications import send_whatsapp_welcome
                    sent, notify_message = send_whatsapp_welcome(name.strip(), cleaned_phone)
                    if not sent:
                        st.caption(notify_message)  # quiet notice, doesn't block registration
                else:
                    st.error(message)

    st.stop()  # prevents the rest of app.py from rendering until authenticated
    return False


def render_logout_button():
    """Drop into the sidebar. Shows the logged-in user's name and a logout button."""
    user = st.session_state.get("user")
    if not user:
        return
    st.caption(f"Signed in as **{user['name']}**")
    st.caption(f"{user['account_type']}: {user['account_number']}")
    if st.button("Log Out", use_container_width=True):
        del st.session_state["user"]
        st.rerun()