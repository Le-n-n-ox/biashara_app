import hashlib
import hmac
import os
import re
import sqlite3
import streamlit as st

DB_PATH = os.getenv("DB_PATH", "ledger.db")


def _get_conn() -> sqlite3.Connection:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_auth_db():
    with _get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL UNIQUE,
            account_type TEXT NOT NULL,
            account_number TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

def _hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hashed.hex(), salt.hex()

def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    salt_bytes = bytes.fromhex(stored_salt)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 100_000)
    return hmac.compare_digest(hashed.hex(), stored_hash)

def _clean_phone(phone: str) -> str:
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
        return True, "Account created. You can now log in."
    except sqlite3.IntegrityError as e:
        err_msg = str(e)
        if "email" in err_msg:
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

def render_auth_gate():
    init_auth_db()

    if st.session_state.get("user"):
        return True

    st.title("Biashara Bookkeeper")
    st.caption("Log in or register to access your ledger.")

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@business.com")
            show_password = st.checkbox("Show password", key="login_show_password")
            password = st.text_input(
                "Password",
                type="default" if show_password else "password",
                placeholder="Enter your password",
            )
            submitted = st.form_submit_button("Log In", type="primary", width="stretch")

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
            submitted = st.form_submit_button("Create Account", type="primary", width="stretch")

        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match.")
            else:
                ok, message = register_user(name, email, phone, account_type, account_number, password)
                if ok:
                    st.success(message)
                else:
                    st.error(message)

    st.stop()
    return False

def render_logout_button():
    user = st.session_state.get("user")
    if not user:
        return
    st.caption(f"Signed in as **{user['name']}**")
    st.caption(f"{user['account_type']}: {user['account_number']}")
    if st.button("Log Out", use_container_width=True):
        del st.session_state["user"]
        st.rerun()