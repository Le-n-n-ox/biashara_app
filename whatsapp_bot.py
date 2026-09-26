import os
import pandas as pd
from fastapi import FastAPI, Form
from twilio.twiml.messaging_response import MessagingResponse

# Import the logic we already built!
from app import process_receipt_pipeline
from database import save_transactions_to_db, load_transactions_from_db

app = FastAPI()

@app.post("/whatsapp")
async def receive_whatsapp_message(Body: str = Form(...)):
    """
    Catches forwarded M-Pesa SMS from Twilio, runs it through our memory cache,
    and saves it to the SQLite database.
    """
    raw_sms = Body.strip()
    
    # 1. Parse using the Fast Path Memory Cache we built in app.py
    new_transactions = process_receipt_pipeline(raw_sms)
    
    resp = MessagingResponse()
    
    if not new_transactions:
        resp.message("❌ Could not extract M-Pesa details. Please ensure you forward the exact SMS.")
        return str(resp)
        
    new_df = pd.DataFrame(new_transactions)
    
    # 2. Prevent Duplicates against the database
    existing_df = load_transactions_from_db()
    if not existing_df.empty:
        new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]
        
    # 3. Save to SQLite and reply to the user
    if not new_df.empty:
        save_transactions_to_db(new_df)
        
        # Calculate summary for the WhatsApp reply
        added_count = len(new_df)
        total_val = new_df["Amount (KES)"].sum()
        
        reply = f"✅ Success! Saved {added_count} transaction(s) totaling KES {total_val:,.2f} to your Biashara ledger."
    else:
        reply = "⚠️ Duplicate detected. This transaction is already in your ledger."
        
    resp.message(reply)
    return str(resp)