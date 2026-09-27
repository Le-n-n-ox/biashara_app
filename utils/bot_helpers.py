import re
import pandas as pd

CATEGORY_KEYWORDS = {
    "inventory": "Inventory / Supplies", "stock": "Inventory / Supplies", "supplies": "Inventory / Supplies",
    "utilities": "Utilities", "power": "Utilities", "electricity": "Utilities", "kplc": "Utilities",
    "rent": "Rent",
    "operating": "Operating Expenses", "transport": "Operating Expenses", "fuel": "Operating Expenses",
    "payroll": "Transfer / Payroll", "salary": "Transfer / Payroll", "wages": "Transfer / Payroll",
    "sales": "Sales / Income", "income": "Sales / Income",
}

_URL_PATTERN = re.compile(r"(https?://|www\.|bit\.ly|tinyurl\.com|t\.co/)", re.IGNORECASE)
_SCAM_PHRASES = (
    "click link", "click here", "claim your", "claim now", "verify your",
    "congratulations", "you have won", "bonus", "update your pin", "confirm your pin",
)

def looks_like_phishing(text: str) -> bool:
    lowered = text.lower()
    if _URL_PATTERN.search(text):
        return True
    return any(phrase in lowered for phrase in _SCAM_PHRASES)

def looks_like_receipt(text: str) -> bool:
    """Cheap pre-check so obviously-non-receipt text never triggers an AI call."""
    lowered = text.lower()
    if "confirmed" in lowered and any(
        phrase in lowered for phrase in ("sent to", "paid to", "received")
    ):
        return True
    return bool(re.search(r"^[A-Z0-9]{8,12}\b", text.strip(), re.MULTILINE))

def guess_category_from_reply(text: str) -> str | None:
    lowered = text.strip().lower()
    for keyword, category in CATEGORY_KEYWORDS.items():
        if keyword in lowered:
            return category
    return None

def describe_transaction(tx: pd.Series) -> tuple[str, bool]:
    """Builds one friendly line for a transaction. Returns (line, needs_clarification)."""
    amount = tx["Amount (KES)"]
    entity = tx["Entity"]
    category = tx.get("Category", "Unknown")
    channel = tx.get("Channel", "Unknown")
    verb = "received from" if tx["Type"] == "Income" else "paid to"

    unclear = (entity == "UNKNOWN") or (not category) or (category == "Unknown")
    line = f"Logged KES {amount:,.2f} {verb} {entity}"
    if channel and channel not in ("Received", "Unknown"):
        line += f" via {channel}"
    line += " — not sure how to categorize this one." if unclear else f" (tagged as {category})."
    return line, unclear