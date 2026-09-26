"""
Shared receipt-processing logic used by both the Streamlit app (app.py)
and the WhatsApp webhook (whatsapp_bot.py).

Deliberately has NO import of streamlit or any UI module, so it can be
safely imported from a plain FastAPI/uvicorn process without pulling in
st.set_page_config(), init_db() side effects, or a ScriptRunContext error.
"""
import re
from datetime import datetime

from utils.ai_router import process_sms_with_ai
from utils.fraud_detector import analyze_mpesa_fraud
from database import get_entity_memory, update_entity_memory


def infer_channel(line: str) -> str:
    """Distinguishes how the money moved, based on M-Pesa's own SMS wording:
    - 'sent to NAME PHONE' (no account ref)      -> Send Money
    - 'sent to BUSINESS for account ...'         -> Paybill
    - 'paid to BUSINESS' (Buy Goods/Till)        -> Till (Buy Goods)
    - 'received Ksh...'                          -> Received
    """
    lowered = line.lower()
    if "received ksh" in lowered:
        return "Received"
    if "sent to" in lowered:
        return "Paybill" if "for account" in lowered else "Send Money"
    if "paid to" in lowered:
        return "Till (Buy Goods)"
    return "Unknown"


def process_receipt_pipeline(raw_text: str) -> list[dict]:
    """Rule-based (no AI) parser. Includes an inline fraud-detection guard,
    so any caller of this function already gets suspicious lines filtered out."""
    parsed_data = []
    for line in raw_text.splitlines():
        line = line.strip()
        txn_match = re.search(r"^([A-Z0-9]{8,12})\b", line)

        # A real Safaricom transaction code always mixes letters and digits
        # (e.g. "QGH7XJ2K1"); a plain word like "CONFIRMED" matches the same
        # character class but has zero digits. Reject the latter.
        code_has_digit = bool(txn_match) and any(ch.isdigit() for ch in txn_match.group(1))

        # Real M-Pesa confirmations never contain links. A URL is a hard
        # signal of phishing regardless of what fraud_detector.py decides.
        contains_url = bool(re.search(r"(https?://|www\.|bit\.ly|tinyurl\.com|t\.co/)", line, re.IGNORECASE))

        if not txn_match or not code_has_digit or contains_url or analyze_mpesa_fraud(line)["is_suspicious"]:
            continue

        date_match = re.search(r"\bon (\d{1,2}/\d{1,2}/\d{2})\b", line)
        transaction_date = (
            datetime.strptime(date_match.group(1), "%d/%m/%y").strftime("%Y-%m-%d")
            if date_match else datetime.now().strftime("%Y-%m-%d")
        )

        lower_line = line.lower()
        if "received ksh" in lower_line:
            txn_type = "Income"
            amount_match = re.search(r"received\s+Ksh\s?([\d,]+\.\d{2})", line, re.IGNORECASE)
            entity_match = re.search(r"from (.*?)\s+\d{10}\s+on", line, re.IGNORECASE) or re.search(r"from (.*?) on", line, re.IGNORECASE)
        elif "sent to" in lower_line:
            txn_type = "Expense"
            amount_match = re.search(r"Ksh\s?([\d,]+\.\d{2}) sent to", line, re.IGNORECASE)
            entity_match = re.search(r"sent to (.*?)(?: for account\b| on\b)", line, re.IGNORECASE)
        elif "paid to" in lower_line:
            txn_type = "Expense"
            amount_match = re.search(r"Ksh\s?([\d,]+\.\d{2}) paid to", line, re.IGNORECASE)
            entity_match = re.search(r"paid to (.*?) on", line, re.IGNORECASE)
        else:
            continue

        if not amount_match:
            continue
        amount = float(amount_match.group(1).replace(",", ""))
        entity = entity_match.group(1).strip() if entity_match else "UNKNOWN"
        entity_upper = entity.upper()

        if any(name in entity_upper for name in ("SUPERMARKET", "CARREFOUR", "ZUCCHINI", "CHANDARANA", "FOODPLUS", "WHOLESALER")):
            category = "Inventory / Supplies"
        elif any(name in entity_upper for name in ("KPLC", "POWER")):
            category = "Utilities"
        elif any(name in entity_upper for name in ("JAVA", "SHELL", "UBER")):
            category = "Operating Expenses"
        elif txn_type == "Income":
            category = "Sales / Income"
        else:
            category = "Transfer / Payroll"

        parsed_data.append({
            "Transaction Code": txn_match.group(1),
            "Date": transaction_date,
            "Entity": entity,
            "Type": txn_type,
            "Amount (KES)": amount,
            "Category": category,
            "Channel": infer_channel(line),
        })
    return parsed_data


def process_with_ai(raw_text: str, provider: str) -> list[dict]:
    """AI-assisted parser with entity-memory categorization. Falls back to the
    rule-based parser's own results when the AI returns nothing usable."""
    parsed_data = process_receipt_pipeline(raw_text)
    ai_data = process_sms_with_ai(raw_text, provider)

    if not parsed_data:
        codes = re.findall(r"^([A-Z0-9]{8,12})\b", raw_text, re.MULTILINE)
        lines = raw_text.splitlines()
        for index, item in enumerate(ai_data):
            if index >= len(codes):
                continue
            line = lines[index] if index < len(lines) else ""

            # The AI model has no concept of fraud -- it just extracts fields
            # from whatever text it's given. Without this check, a scam message
            # that the rule-based parser correctly rejected (which is WHY we
            # ended up in this AI-fallback branch at all) would sail straight
            # through here unchecked. Apply the same guards as the rule-based path.
            code = str(item.get("Transaction Code", codes[index]))
            code_has_digit = any(ch.isdigit() for ch in code)
            contains_url = bool(re.search(r"(https?://|www\.|bit\.ly|tinyurl\.com|t\.co/)", line, re.IGNORECASE))
            if not code_has_digit or contains_url or analyze_mpesa_fraud(line)["is_suspicious"]:
                continue

            try:
                amount = float(str(item.get("Amount (KES)", item.get("Amount", 0))).replace(",", ""))
            except (TypeError, ValueError):
                continue
            parsed_data.append({
                "Transaction Code": item.get("Transaction Code", codes[index]),
                "Date": item.get("Date", datetime.now().strftime("%Y-%m-%d")),
                "Entity": item.get("Entity", "UNKNOWN"),
                "Type": item.get("Type", "Income" if "received" in line.lower() else "Expense"),
                "Amount (KES)": amount,
                "Category": item.get("Category", "Unknown"),
                "Channel": item.get("Channel", infer_channel(line)),
            })
    else:
        for index, item in enumerate(ai_data):
            if index < len(parsed_data) and item.get("Category"):
                parsed_data[index]["Category"] = item["Category"]

    memory = get_entity_memory()
    for tx in parsed_data:
        entity = tx["Entity"].strip().upper()
        if entity in memory:
            tx["Category"] = memory[entity]
        elif entity and tx.get("Category"):
            update_entity_memory(entity, tx["Category"])
    return parsed_data