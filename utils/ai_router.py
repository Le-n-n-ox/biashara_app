import os
import json
from openai import OpenAI
from google import genai
import ollama
from pydantic import BaseModel

# --- External Pydantic Blueprint ---
class Transaction(BaseModel):
    Date: str
    Amount: int
    Entity: str
    Category: str

class Ledger(BaseModel):
    transactions: list[Transaction]

def process_sms_with_ai(sms_input: str, model_provider: str) -> list[dict]:
    """
    Sends raw SMS text to the selected AI provider (NVIDIA, GEMINI, or OLLAMA)
    and returns a clean list of transaction dictionaries.
    """
    prompt = f"""
    Extract transaction data from these M-Pesa SMS messages.
    DO NOT write Python code. DO NOT explain your answer.
    
    Return ONLY a raw JSON array of objects with these exact keys:
    - "Date": string (e.g. "27/9/26")
    - "Amount": integer (numeric KES amount only)
    - "Entity": string (Sender/Recipient name)
    - "Category": string ("Supplies", "Transport", "Sales", or "Utilities")

    Messages:
    {sms_input}
    """
    
    raw_output = ""
    
    # --- AI Provider Routing ---
    if model_provider == "NVIDIA":
        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"))
        response = client.chat.completions.create(
            model="meta/llama3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        raw_output = response.choices[0].message.content
        
    elif model_provider == "GEMINI":
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        raw_output = response.text
        
    elif model_provider == "OLLAMA":
        local_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        response = ollama.chat(
            model=local_model, 
            messages=[{'role': 'user', 'content': prompt}],
            format=Ledger.model_json_schema()
        )
        raw_output = response['message']['content']
    else:
        raise ValueError(f"Invalid MODEL_PROVIDER: {model_provider}")

    # --- Output Parsing & Cleaning ---
    if model_provider == "OLLAMA":
        parsed = json.loads(raw_output)
        return parsed.get("transactions", [])
    else:
        raw_output = raw_output.strip()
        if raw_output.startswith("```json"): 
            raw_output = raw_output[7:]
        if raw_output.startswith("```"): 
            raw_output = raw_output[3:]
        if raw_output.endswith("```"): 
            raw_output = raw_output[:-3]
        
        start_idx = raw_output.find('[')
        end_idx = raw_output.rfind(']')
        if start_idx != -1 and end_idx != -1:
            raw_output = raw_output[start_idx:end_idx + 1]

        data_list = json.loads(raw_output)
        
        if isinstance(data_list, dict):
            if "Amount" in data_list:
                data_list = [data_list]
            else:
                for key, val in data_list.items():
                    if isinstance(val, list):
                        data_list = val
                        break
                        
        return data_list