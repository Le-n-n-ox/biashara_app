import os
import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from utils.parsing import process_receipt_pipeline, process_with_ai
from database import save_transactions_to_db, load_transactions_from_db, get_entity_memory

router = APIRouter()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").strip().upper()

class SMSForwarderPayload(BaseModel):
    sender: str
    message: str

@router.post("/api/auto-receipt/sms")
async def receive_forwarded_sms(payload: SMSForwarderPayload):
    if payload.sender.strip().upper() != "MPESA":
        return {"status": "ignored", "reason": "Sender is not MPESA"}

    try:
        transactions = process_with_ai(payload.message, MODEL_PROVIDER)
    except Exception:
        transactions = process_receipt_pipeline(payload.message)

    if not transactions:
        return {"status": "failed", "reason": "Could not extract transaction data"}

    new_df = pd.DataFrame(transactions)
    existing_df = load_transactions_from_db()
    if not existing_df.empty:
        new_df = new_df[~new_df["Transaction Code"].isin(existing_df["Transaction Code"])]

    if not new_df.empty:
        save_transactions_to_db(new_df)
        return {"status": "success", "inserted": len(new_df)}
    
    return {"status": "ignored", "reason": "Duplicate transaction"}


class DarajaC2BPayload(BaseModel):
    TransactionType: str
    TransID: str
    TransTime: str
    TransAmount: float
    BusinessShortCode: str
    BillRefNumber: Optional[str] = ""
    InvoiceNumber: Optional[str] = ""
    OrgAccountBalance: str
    ThirdPartyTransID: Optional[str] = ""
    MSISDN: str
    FirstName: Optional[str] = ""
    MiddleName: Optional[str] = ""
    LastName: Optional[str] = ""

@router.post("/api/daraja/c2b/validation")
async def daraja_validation(payload: dict):
    return {"ResultCode": 0, "ResultDesc": "Accepted"}

@router.post("/api/daraja/c2b/confirmation")
async def daraja_confirmation(payload: DarajaC2BPayload):
    raw_time = payload.TransTime
    formatted_date = f"{raw_time[:4]}-{raw_time[4:6]}-{raw_time[6:8]}" if len(raw_time) >= 8 else raw_time

    entity_name = f"{payload.FirstName} {payload.LastName}".strip().upper()
    entity = f"{entity_name} - {payload.MSISDN}" if entity_name else payload.MSISDN

    memory = get_entity_memory()
    category = memory.get(entity, "Sales / Income")

    new_tx = pd.DataFrame([{
        "Transaction Code": payload.TransID,
        "Date": formatted_date,
        "Entity": entity,
        "Type": "Income",
        "Amount (KES)": float(payload.TransAmount),
        "Category": category,
        "Channel": payload.TransactionType 
    }])

    existing_df = load_transactions_from_db()
    if not existing_df.empty:
        new_tx = new_tx[~new_tx["Transaction Code"].isin(existing_df["Transaction Code"])]

    if not new_tx.empty:
        save_transactions_to_db(new_tx)

    return {"ResultCode": 0, "ResultDesc": "Success"}