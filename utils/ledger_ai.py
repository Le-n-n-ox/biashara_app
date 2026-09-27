import os
import re
import json
import pandas as pd
from openai import OpenAI
from google import genai
import ollama

def ask_ledger_ai(
    user_message: str,
    ledger_df: pd.DataFrame,
    provider: str = "OLLAMA",
    conversation_history=None
):

    if ledger_df.empty:
        return {
            "reasoning": "Ledger is empty.",
            "confidence": 100,
            "needs_clarification": False,
            "response": "Your ledger is currently empty. Process some M-Pesa receipts first!"
        }

    if conversation_history is None:
        conversation_history = []

    # Convert last 500 records into structured JSON for AI reasoning
    ledger_data = (
        ledger_df
        .fillna("")
        .tail(500)
        .to_dict(orient="records")
    )

    entities = sorted(list(set(ledger_df["Entity"].dropna().astype(str).tolist())))
    categories = sorted(list(set(ledger_df["Category"].dropna().astype(str).tolist())))

    # --- THE FIX: Format history as a readable transcript instead of raw JSON ---
    history_transcript = ""
    for turn in conversation_history:
        history_transcript += f"User: {turn.get('user', '')}\nAssistant: {turn.get('assistant', '')}\n\n"
    
    if not history_transcript.strip():
        history_transcript = "No previous conversation."

    prompt = f"""
You are Biashara Bookkeeper AI, an expert financial analyst for small businesses in Kenya.

YOUR SOURCE OF TRUTH (LEDGER RECORDS):
{json.dumps(ledger_data, default=str)}

Known Entities: {entities}
Known Categories: {categories}

CONVERSATION HISTORY (For Context & Pronouns):
{history_transcript}

CURRENT USER QUESTION:
"{user_message}"

INSTRUCTIONS & REASONING RULES:

1. CONTEXT & PRONOUNS (CRITICAL):
   - ALWAYS read the CONVERSATION HISTORY. 
   - If the user uses pronouns like "them", "he", "her", "they", or "that", resolve it based on the immediately preceding turns. 
   - Example: If the user previously asked about "Mary and David", and now asks "did I receive money from them?", "them" refers to Mary and David. DO NOT ask for clarification if the history provides the answer.

2. PARTIAL & FUZZY NAME MATCHING:
   - Match names flexibly (case-insensitive, first names, or keywords).

3. PHONE NUMBER & CONTACT LOOKUPS:
   - Phone numbers (07xx or 01xx) are embedded in the "Entity" strings. Extract and report them if asked.

4. MULTI-ENTITY & COMBINED CALCULATIONS:
   - Identify ALL relevant transactions for the requested entities.
   - Explicitly sum the amounts step-by-step in your internal reasoning.
   - Report individual breakdowns and the grand total clearly in your final response.

5. ACCURACY & HONESTY:
   - Never invent transactions. If a person does not exist in the ledger, state clearly that no records were found.

REQUIRED OUTPUT FORMAT:
You MUST return valid JSON ONLY. Use this exact schema:

{{
  "reasoning": "Write step-by-step record lookups, resolve pronouns from the history, and perform explicit math calculations here.",
  "confidence": 95,
  "needs_clarification": false,
  "response": "Friendly, well-formatted final response with KES values, breakdowns, and bullet points where helpful."
}}
"""

    try:
        provider = provider.upper()

        if provider == "OLLAMA":
            response = ollama.chat(
                model=os.getenv("OLLAMA_MODEL", "llama3.2"),
                messages=[{"role": "user", "content": prompt}],
                format="json"
            )
            content = response.message.content

        elif provider == "GEMINI":
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            content = response.text

        else:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content

        # Clean markdown wrappers if model returns ```json ... ```
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        start = content.find("{")
        end = content.rfind("}") + 1

        if start != -1 and end > start:
            return json.loads(content[start:end])
        
        return {
            "reasoning": "Failed to locate valid JSON brackets in model output.",
            "confidence": 0,
            "needs_clarification": True,
            "response": "I couldn't process that ledger query clearly. Please try asking again."
        }

    except Exception as e:
        return {
            "reasoning": f"Exception encountered: {str(e)}",
            "confidence": 0,
            "needs_clarification": True,
            "response": f"Error querying ledger AI: {str(e)}"
        }