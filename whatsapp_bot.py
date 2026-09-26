import os
import re
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

# Separate pending state for "I wasn't sure what you meant, did you want X?"
# confirmations -- keyed by sender, value is the original ambiguous text.
PENDING_AMBIGUOUS: dict[str, str] = {}

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

# Same-spirit checks as the ones added to parsing.py's process_receipt_pipeline,
# duplicated here so the bot can give a specific, friendly phishing warning
# instead of the generic "couldn't parse that" fallback.
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


QUERY_KEYWORDS = ("show", "list", "last", "recent", "total", "balance", "summary", "history", "how much", "find", "search")


def is_query(text: str) -> bool:
    lowered = text.strip().lower()
    return any(keyword in lowered for keyword in QUERY_KEYWORDS)


_QUERY_STOPWORDS = {
    "show", "me", "my", "list", "the", "a", "an", "please", "transactions", "transaction",
    "logs", "log", "records", "record", "all", "i", "made", "did", "have", "has",
    "with", "for", "about", "regarding", "find", "search", "what", "whats", "is", "of", "on", "do", "did",
    "hey", "hi", "hello", "are", "you", "there", "thanks", "thank", "ok", "okay", "pls",
}


def extract_search_term(text: str) -> str:
    """Pulls the likely subject out of a loosely-phrased query, e.g.
    'show me transactions i made to David Omondi' -> 'david omondi'."""
    lowered = text.strip().lower().strip(" ?!.")
    # Prefer whatever follows a directional preposition -- this is usually the actual subject
    match = re.search(r"\b(?:to|from|with|about|regarding)\s+(.+)$", lowered)
    candidate = match.group(1) if match else lowered
    candidate = candidate.strip(" ?!.")
    tokens = [t for t in candidate.split() if t not in _QUERY_STOPWORDS]
    return " ".join(tokens)


def find_known_mention(text: str, df: pd.DataFrame) -> str | None:
    """Checks whether the message mentions any entity or category that's
    ALREADY in the ledger. This generalizes far beyond a fixed keyword list --
    if someone asks about a name they've actually transacted with, in any
    phrasing, this catches it without needing to guess every possible wording."""
    if df.empty:
        return None
    lowered = text.lower()
    for value in pd.concat([df["Entity"], df["Category"]]).dropna().unique():
        value = str(value).strip()
        if value and value.lower() in lowered:
            return value
    return None


# Fields people might ask for that the ledger simply doesn't store. Answering
# honestly here beats endlessly asking for clarification on something no
# amount of rephrasing will ever find.
_UNAVAILABLE_FIELD_KEYWORDS = {
    "number": "phone numbers or contact details",
    "phone": "phone numbers or contact details",
    "contact": "phone numbers or contact details",
    "mobile": "phone numbers or contact details",
    "address": "physical addresses",
    "email": "email addresses",
}


def handle_query(text: str, known_mention: str | None = None) -> str:
    """Answers questions about transactions already in the ledger."""
    lowered = text.strip().lower()
    df = load_transactions_from_db()
    if df.empty:
        return "Your ledger is empty so far — forward an M-Pesa SMS to get started."

    if any(word in lowered for word in ("total", "balance", "summary")) and not known_mention:
        income = df.loc[df["Type"] == "Income", "Amount (KES)"].sum()
        expenses = df.loc[df["Type"] == "Expense", "Amount (KES)"].sum()
        net = income - expenses
        return (
            f"📊 Summary so far:\nReceived: KES {income:,.2f}\n"
            f"Spent: KES {expenses:,.2f}\nNet: KES {net:,.2f}"
        )

    if any(word in lowered for word in ("last", "recent")) and not known_mention:
        count_match = re.search(r"last (\d+)", lowered)
        n = min(int(count_match.group(1)), 10) if count_match else 3
        recent = df.tail(n)
        lines = []
        for _, tx in recent.iterrows():
            verb = "from" if tx["Type"] == "Income" else "to"
            lines.append(f"• KES {tx['Amount (KES)']:,.2f} {verb} {tx['Entity']} ({tx['Category']}) on {tx['Date']}")
        return f"🧾 Your last {len(recent)} transaction(s):\n" + "\n".join(lines)

    # Prefer an exact known entity/category match over the fuzzy extractor --
    # it's more reliable when we already know it's a real name from the ledger.
    search_term = (known_mention or extract_search_term(text)).lower()
    matches = df[
        df["Entity"].str.lower().str.contains(search_term, na=False, regex=False)
        | df["Category"].str.lower().str.contains(search_term, na=False, regex=False)
    ] if search_term else pd.DataFrame()

    if not matches.empty:
        lines = []
        for _, tx in matches.tail(5).iterrows():
            verb = "from" if tx["Type"] == "Income" else "to"
            lines.append(f"• KES {tx['Amount (KES)']:,.2f} {verb} {tx['Entity']} ({tx['Category']}) on {tx['Date']}")
        results_block = "\n".join(lines)

        for keyword, field_name in _UNAVAILABLE_FIELD_KEYWORDS.items():
            if keyword in lowered:
                return (
                    f"I don't store {field_name} — only transaction records "
                    f"(amount, date, category, channel). Here's what I do have "
                    f"for '{search_term}':\n{results_block}"
                )

        return f"🔎 Found {len(matches)} matching transaction(s) for '{search_term}':\n{results_block}"

    if search_term:
        return f"I couldn't find anything matching '{search_term}'. Try 'show my last 3 transactions' or 'what's my total'."
    return "I couldn't tell what you're looking for. Try 'show my last 3 transactions', 'what's my total', or a name/category to search for."


AFFIRMATIVE_REPLIES = {"yes", "yeah", "yep", "yup", "sure", "correct", "please", "please do", "ok", "okay"}
NEGATIVE_REPLIES = {"no", "nah", "nope", "never mind", "cancel"}


def looks_like_receipt(text: str) -> bool:
    """Cheap pre-check so obviously-non-receipt text (a bare name, small talk,
    an ambiguous fragment) never triggers an AI call at all -- only messages
    that plausibly ARE a forwarded M-Pesa SMS do."""
    lowered = text.lower()
    if "ksh" in lowered or "confirmed" in lowered:
        return True
    return bool(re.search(r"^[A-Z0-9]{8,12}\b", text.strip(), re.MULTILINE))


def ambiguous_clarification_reply(raw_text: str, sender: str) -> str:
    """Stores the pending ambiguous message and returns a clarifying question,
    phrased generically when no clear subject could be extracted."""
    search_term = extract_search_term(raw_text)
    PENDING_AMBIGUOUS[sender] = raw_text
    if search_term:
        return (
            f"I'm not sure what you meant. Did you want me to look up transactions "
            f"related to '{search_term}'? Reply yes/no — or forward the exact M-Pesa "
            f"SMS to log a new transaction."
        )
    return (
        "I'm not sure what you meant by that. Forward an M-Pesa SMS to log a "
        "transaction, or ask something like 'show my last 3 transactions' or "
        "'what's my total'."
    )


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


@app.post("/whatsapp")
async def receive_whatsapp_message(Body: str = Form(...), From: str = Form(...)):
    raw_text = Body.strip()
    resp = MessagingResponse()

    # --- 0. Phishing check, before anything else. Real Safaricom messages never
    # contain links or ask you to "claim" or "verify" anything. ---
    if looks_like_phishing(raw_text):
        resp.message(
            "⚠️ This looks like a phishing message, not a real M-Pesa confirmation. "
            "Safaricom SMS never contain links or ask you to click, claim, or verify "
            "anything. I have not logged this — please don't tap that link, and "
            "consider blocking the sender."
        )
        return Response(content=str(resp), media_type="application/xml")

    # --- 1. If we're waiting on a category clarification from this exact sender, resolve it first ---
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

    # --- 1.5 If we asked "did you mean...?" last time, check for a yes/no answer ---
    pending_text = PENDING_AMBIGUOUS.get(From)
    if pending_text:
        lowered_reply = raw_text.strip().lower()
        if lowered_reply in AFFIRMATIVE_REPLIES:
            del PENDING_AMBIGUOUS[From]
            resp.message(handle_query(pending_text))
            return Response(content=str(resp), media_type="application/xml")
        elif lowered_reply in NEGATIVE_REPLIES:
            del PENDING_AMBIGUOUS[From]
            resp.message("No problem — send a new M-Pesa SMS or ask me anything about your ledger any time.")
            return Response(content=str(resp), media_type="application/xml")
        else:
            # Not a yes/no -- drop the pending question and process this as a fresh message
            del PENDING_AMBIGUOUS[From]

    # --- 2. Does this actually look like a forwarded M-Pesa SMS? Check this FIRST,
    # before the query check -- every real M-Pesa message contains the word
    # "balance" ("New M-PESA balance is Ksh..."), which would otherwise falsely
    # match the query keyword list on every single legitimate receipt. ---
    receipt_shaped = looks_like_receipt(raw_text)
    mention = None if receipt_shaped else find_known_mention(raw_text, load_transactions_from_db())

    if receipt_shaped:
        try:
            transactions = process_with_ai(raw_text, MODEL_PROVIDER)
        except Exception:
            transactions = process_receipt_pipeline(raw_text)  # offline/AI-down fallback

        if not transactions:
            # Looked like a receipt but didn't actually parse -- ask rather than reject flatly.
            resp.message(ambiguous_clarification_reply(raw_text, From))
            return Response(content=str(resp), media_type="application/xml")
    elif is_query(raw_text) or mention:
        # Doesn't look like a receipt, but does look like a question -- or it
        # mentions a real name/category from the ledger, whatever the phrasing.
        # Answer straight from the ledger, never touching the AI.
        resp.message(handle_query(raw_text, known_mention=mention))
        return Response(content=str(resp), media_type="application/xml")
    else:
        # Neither a receipt nor a recognized query -- ask what they meant.
        resp.message(ambiguous_clarification_reply(raw_text, From))
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