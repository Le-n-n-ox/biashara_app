import os
import concurrent.futures
import pandas as pd
from fastapi import APIRouter, Form, Response
from twilio.twiml.messaging_response import MessagingResponse

from utils.parsing import process_receipt_pipeline, process_with_ai
from utils.ledger_ai import ask_ledger_ai
from database import save_transactions_to_db, load_transactions_from_db, update_entity_memory, update_transaction_category
from utils.bot_helpers import looks_like_phishing, looks_like_receipt, guess_category_from_reply, describe_transaction

router = APIRouter()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").strip().upper()
AI_QA_TIMEOUT_SECONDS = 8 

PENDING_CLARIFICATION: dict[str, dict] = {}
PENDING_AMBIGUOUS: dict[str, str] = {}
AI_CONTEXT: dict[str, list] = {}

AFFIRMATIVE_REPLIES = {"yes", "yeah", "yep", "yup", "sure", "correct", "please", "please do", "ok", "okay"}
NEGATIVE_REPLIES = {"no", "nah", "nope", "never mind", "cancel"}

def handle_ai_query(text: str, sender: str) -> str:
    df = load_transactions_from_db()
    history = AI_CONTEXT.get(sender, [])

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            ask_ledger_ai,
            user_message=text,
            ledger_df=df,
            provider=MODEL_PROVIDER,
            conversation_history=history,
        )
        try:
            result = future.result(timeout=AI_QA_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            return "That's taking longer than expected to look up — the AI provider might be slow or unreachable right now. Try again in a moment."
        except Exception:
            return "Something went wrong answering that. Try rephrasing, or ask again in a moment."

    response = result.get("response", "Sorry, I couldn't process that request.")
    history.append({"user": text, "assistant": response})
    AI_CONTEXT[sender] = history[-10:]
    return response

def ambiguous_clarification_reply(raw_text: str, sender: str) -> str:
    PENDING_AMBIGUOUS[sender] = raw_text
    return "I'm not sure I understood. Could you rephrase your request or tell me exactly what you want to know?"

@router.post("/whatsapp")
async def receive_whatsapp_message(Body: str = Form(...), From: str = Form(...)):
    resp = MessagingResponse()
    
    try:
        raw_text = Body.strip()

        if looks_like_phishing(raw_text):
            resp.message(
                "⚠️ This looks like a phishing message, not a real M-Pesa confirmation. "
                "I have not logged this — please don't tap any links."
            )
            return Response(content=str(resp), media_type="application/xml")

        pending = PENDING_CLARIFICATION.get(From)
        if pending:
            category = guess_category_from_reply(raw_text)
            if category:
                update_entity_memory(pending["entity"], category)
                update_transaction_category(pending["code"], category)
                del PENDING_CLARIFICATION[From]
                resp.message(f"Got it — tagged with {pending['entity']} as '{category}'.")
            else:
                resp.message("I didn't catch a category in that. Reply with one word (e.g. 'Rent', 'Transport').")
            return Response(content=str(resp), media_type="application/xml")

        pending_text = PENDING_AMBIGUOUS.get(From)
        if pending_text:
            lowered_reply = raw_text.strip().lower()
            if lowered_reply in AFFIRMATIVE_REPLIES:
                del PENDING_AMBIGUOUS[From]
                resp.message(handle_ai_query(pending_text, From))
                return Response(content=str(resp), media_type="application/xml")
            elif lowered_reply in NEGATIVE_REPLIES:
                del PENDING_AMBIGUOUS[From]
                resp.message("No problem — send a new M-Pesa SMS any time.")
                return Response(content=str(resp), media_type="application/xml")
            else:
                del PENDING_AMBIGUOUS[From]

        receipt_shaped = looks_like_receipt(raw_text)

        if receipt_shaped:
            try:
                transactions = process_with_ai(raw_text, MODEL_PROVIDER)
            except Exception as ai_err:
                print(f"AI Parsing failed: {ai_err}")
                transactions = process_receipt_pipeline(raw_text) 

            if not transactions:
                resp.message(ambiguous_clarification_reply(raw_text, From))
                return Response(content=str(resp), media_type="application/xml")
        else:
            answer = handle_ai_query(raw_text, From)
            resp.message(answer)
            return Response(content=str(resp), media_type="application/xml")

        # Database Insertion
        new_df = pd.DataFrame(transactions)
        existing_df = load_transactions_from_db()
        if not existing_df.empty:
            new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]

        if new_df.empty:
            resp.message("Looks like I've already logged this one — no duplicate added.")
            return Response(content=str(resp), media_type="application/xml")

        save_transactions_to_db(new_df)

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

    except Exception as e:
        # If ANYTHING crashes above, this guarantees Twilio will text you the error!
        error_msg = f"Oops! The bot crashed: {str(e)}"
        print(error_msg)
        resp.message(error_msg)
        return Response(content=str(resp), media_type="application/xml")