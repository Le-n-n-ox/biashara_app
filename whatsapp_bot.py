import os
import pandas as pd
from fastapi import FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

from utils.parsing import process_receipt_pipeline, process_with_ai
from database import save_transactions_to_db, load_transactions_from_db, update_entity_memory, update_transaction_category

load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").strip().upper()

app = FastAPI()

# In-memory "waiting on a reply from this person" state, keyed by WhatsApp
# sender number. Resets on server restart -- fine for a demo; move this to
# a small database table if you need it to survive redeploys.
PENDING_CLARIFICATION: dict[str, dict] = {}

# Keyword -> canonical category, used to interpret a person's free-text
# clarification reply ("rent", "utilities", etc.)
CATEGORY_KEYWORDS = {
    "inventory": "Inventory / Supplies", "stock": "Inventory / Supplies", "supplies": "Inventory / Supplies",
    "utilities": "Utilities", "power": "Utilities", "electricity": "Utilities", "kplc": "Utilities",
    "rent": "Rent",
    "operating": "Operating Expenses", "transport": "Operating Expenses", "fuel": "Operating Expenses",
    "payroll": "Transfer / Payroll", "salary": "Transfer / Payroll", "wages": "Transfer / Payroll",
    "sales": "Sales / Income", "income": "Sales / Income",
}


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
    verb = "received from" if tx["Type"] == "Income" else "paid to"

    unclear = (entity == "UNKNOWN") or (not category) or (category == "Unknown")
    line = f"Logged KES {amount:,.2f} {verb} {entity}"
    line += " — not sure how to categorize this one." if unclear else f" (tagged as {category})."
    return line, unclear


@app.post("/whatsapp")
async def receive_whatsapp_message(Body: str = Form(...), From: str = Form(...)):
    raw_text = Body.strip()
    resp = MessagingResponse()

    # --- 1. If we're waiting on a clarification from this exact sender, try to resolve it first ---
    pending = PENDING_CLARIFICATION.get(From)
    if pending:
        category = guess_category_from_reply(raw_text)
        if category:
            update_entity_memory(pending["entity"], category)
            update_transaction_category(pending["code"], category)
            del PENDING_CLARIFICATION[From]
            resp.message(
                f"Got it — tagged the KES {pending['amount']:,.2f} transaction with "
                f"{pending['entity']} as '{category}'. Future transactions with this "
                f"entity will auto-categorize the same way."
            )
        else:
            resp.message(
                "I didn't catch a category in that. Reply with one word, e.g. "
                "'Inventory', 'Utilities', 'Rent', 'Transport' or 'Payroll' — "
                "or send a new receipt any time and I'll come back to this."
            )
        return Response(content=str(resp), media_type="application/xml")

    # --- 2. Otherwise, treat this as a new receipt ---
    try:
        transactions = process_with_ai(raw_text, MODEL_PROVIDER)
    except Exception:
        transactions = process_receipt_pipeline(raw_text)  # offline/AI-down fallback

    if not transactions:
        resp.message(
            "I couldn't find an M-Pesa transaction in that message. Could you "
            "forward the exact SMS, unedited? It should start with a transaction "
            "code, like 'QGH7XJ2K1 Confirmed...'."
        )
        return Response(content=str(resp), media_type="application/xml")

    new_df = pd.DataFrame(transactions)
    existing_df = load_transactions_from_db()
    if not existing_df.empty:
        new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]

    if new_df.empty:
        resp.message("Looks like I've already logged this one — no duplicate added.")
        return Response(content=str(resp), media_type="application/xml")

    save_transactions_to_db(new_df)

    # --- 3. Build the reply, and flag the first unclear transaction for follow-up ---
    lines = []
    for _, tx in new_df.iterrows():
        line, unclear = describe_transaction(tx)
        lines.append(line)
        if unclear and From not in PENDING_CLARIFICATION:
            PENDING_CLARIFICATION[From] = {
                "code": tx["Transaction Code"],
                "entity": tx["Entity"],
                "amount": tx["Amount (KES)"],
            }

    reply = "✅ " + "\n".join(lines)
    if From in PENDING_CLARIFICATION:
        reply += "\n\nWhat category should that unclear one be? (e.g. Inventory, Utilities, Rent)"

    resp.message(reply)
    return Response(content=str(resp), media_type="application/xml")