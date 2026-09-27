import psycopg2
import hashlib
import hmac
import os
import re
import streamlit as st
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException
from dotenv import load_dotenv

load_dotenv()

# Common countries for the dropdown -- name shown to user, ISO region code
# phonenumbers uses internally.
COUNTRIES = {
    "Kenya (+254)": "KE",
    "Uganda (+256)": "UG",
    "Tanzania (+255)": "TZ",
    "Rwanda (+250)": "RW",
    "Nigeria (+234)": "NG",
    "South Africa (+27)": "ZA",
    "Ghana (+233)": "GH",
    "Ethiopia (+251)": "ET",
    "United States (+1)": "US",
    "United Kingdom (+44)": "GB",
    "India (+91)": "IN",
}
DEFAULT_COUNTRY_LABEL = "Kenya (+254)"


@st.cache_resource
def _get_conn():
    """Cached across reruns: psycopg2 connections aren't cheap to open
    (TCP handshake + TLS + auth round-trip), so st.cache_resource keeps
    one alive for the life of the app process instead of reconnecting
    on every single query -- this is what was making login slow."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        try:
            db_url = st.secrets["DATABASE_URL"]
        except Exception:
            pass
    if not db_url:
        raise ValueError("DATABASE_URL environment variable or secret is not set")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def _reconnect_if_needed(conn):
    """psycopg2 connections can go stale (dropped by the DB host after
    idle timeout, network blip, etc.). Cheap liveness check before use;
    clears the cache and reconnects once if the connection is dead."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return conn
    except psycopg2.OperationalError:
        _get_conn.clear()
        return _get_conn()


def init_auth_db():
    conn = _reconnect_if_needed(_get_conn())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL UNIQUE,
            account_type TEXT NOT NULL,
            account_number TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cursor.close()


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hashed.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    salt_bytes = bytes.fromhex(stored_salt)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 100_000)
    return hmac.compare_digest(hashed.hex(), stored_hash)


def _normalize_phone(raw_phone: str, region: str) -> tuple[str | None, str | None]:
    """Parses a phone number against the given country (ISO region code, e.g.
    'KE', 'US') and returns (E.164 string, None) on success, or
    (None, error message) on failure. E.164 = '+2547XXXXXXXX' format,
    used as the canonical stored/compared form regardless of input style."""
    try:
        parsed = phonenumbers.parse(raw_phone.strip(), region)
    except NumberParseException:
        return None, "Enter a valid phone number for the selected country."

    if not phonenumbers.is_valid_number(parsed):
        return None, "This doesn't look like a valid number for the selected country."

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164), None


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def register_user(name: str, email: str, phone_raw: str, country_region: str,
                   account_type: str, account_number: str, password: str) -> tuple[bool, str]:
    name = name.strip()
    email = email.strip().lower()
    account_number = account_number.strip()

    if not name or len(name) < 2:
        return False, "Please enter your full name."
    if not _is_valid_email(email):
        return False, "Enter a valid email address."

    phone, phone_error = _normalize_phone(phone_raw, country_region)
    if phone_error:
        return False, phone_error

    if account_type not in ("Till", "Paybill"):
        return False, "Select whether this is a Till or Paybill number."
    if not account_number or not account_number.isdigit():
        return False, f"{account_type} number should contain digits only."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    password_hash, salt = _hash_password(password)

    conn = _reconnect_if_needed(_get_conn())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO users (name, email, phone, account_type, account_number, password_hash, salt)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (name, email, phone, account_type, account_number, password_hash, salt),
        )
        conn.commit()
        cursor.close()
        return True, "Account created. You can now log in."
    except psycopg2.IntegrityError as e:
        conn.rollback()
        err_msg = str(e)
        if "email" in err_msg:
            return False, "This email is already registered."
        return False, "This phone number is already registered."


def authenticate_user(email: str, password: str) -> tuple[bool, str, dict | None]:
    email = email.strip().lower()
    conn = _reconnect_if_needed(_get_conn())
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, name, email, phone, account_type, account_number, password_hash, salt
           FROM users WHERE email = %s""",
        (email,),
    )
    row = cursor.fetchone()
    cursor.close()

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
        # Country selector lives OUTSIDE the form so the phone placeholder/example
        # can update live as the person picks their country -- st.form only
        # re-renders its contents on submit, which would leave a stale example.
        country_label = st.selectbox(
            "Country",
            list(COUNTRIES),
            index=list(COUNTRIES).index(DEFAULT_COUNTRY_LABEL),
            key="register_country",
        )
        country_region = COUNTRIES[country_label]

        example_number = phonenumbers.example_number(country_region)
        example_display = (
            phonenumbers.format_number(example_number, PhoneNumberFormat.NATIONAL)
            if example_number else "712345678"
        )

        with st.form("register_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email", placeholder="you@business.com")
            phone_raw = st.text_input(
                "Phone Number",
                placeholder=example_display,
                help=f"Enter your number as you would dial it within {country_label.split(' (')[0]}.",
            )
            account_type = st.selectbox("Account Type", ["Till", "Paybill"])
            account_number = st.text_input(f"{account_type} Number", placeholder="e.g. 174379")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Account", type="primary", width="stretch")

        if submitted:
            if password != confirm_password:
                st.error("Passwords do not match.")
            else:
                ok, message = register_user(
                    name, email, phone_raw, country_region, account_type, account_number, password
                )
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
    if st.button("Log Out", width="stretch"):
        del st.session_state["user"]
        st.rerun()