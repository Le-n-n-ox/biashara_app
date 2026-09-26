import streamlit as st
import json
import pandas as pd
import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Import AI SDKs
from openai import OpenAI
from google import genai
import ollama

# --- NEW: External Pydantic Blueprint ---
# This forces the AI to always return a list of transactions
class Transaction(BaseModel):
    Date: str
    Amount: int
    Entity: str
    Category: str

class Ledger(BaseModel):
    transactions: list[Transaction]
# ----------------------------------------

load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").upper()

st.set_page_config(page_title="Biashara Bookkeeper", layout="wide")

st.sidebar.header("⚙️ Configuration")
st.sidebar.info(f"**Active Model:** {MODEL_PROVIDER}\n\n*Change `MODEL_PROVIDER` in your `.env` file to switch.*")

st.title("Biashara Bookkeeper 📊")
st.subheader("Paste your daily M-Pesa SMS receipts below:")

sms_input = st.text_area("M-Pesa Messages", height=200, placeholder="Paste raw M-Pesa SMS here...")

if st.button("Analyze Receipts"):
    if sms_input:
        with st.spinner(f"Processing transactions using {MODEL_PROVIDER}..."):
            
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
            data_list = []
            
            try:
                # --- NVIDIA Routing ---
                if MODEL_PROVIDER == "NVIDIA":
                    client = OpenAI(
                        base_url="https://integrate.api.nvidia.com/v1",
                        api_key=os.getenv("NVIDIA_API_KEY")
                    )
                    response = client.chat.completions.create(
                        model="meta/llama3-70b-instruct",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1
                    )
                    raw_output = response.choices[0].message.content
                    
                # --- Google Gemini Routing ---
                elif MODEL_PROVIDER == "GEMINI":
                    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt
                    )
                    raw_output = response.text
                    
                # --- Ollama Routing (Local) ---
                elif MODEL_PROVIDER == "OLLAMA":
                    local_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
                    response = ollama.chat(
                        model=local_model, 
                        messages=[{'role': 'user', 'content': prompt}],
                        # Here we use Pydantic to physically enforce the schema
                        format=Ledger.model_json_schema()
                    )
                    raw_output = response['message']['content']

                else:
                    st.error("Invalid MODEL_PROVIDER in .env file. Use NVIDIA, GEMINI, or OLLAMA.")
                    st.stop()

                # --- Clean and Render Output ---
                if MODEL_PROVIDER == "OLLAMA":
                    # Pydantic guarantees this exact structure: {"transactions": [{...}]}
                    parsed = json.loads(raw_output)
                    data_list = parsed.get("transactions", [])
                else:
                    # Basic cleanup for Cloud models
                    raw_output = raw_output.strip()
                    if raw_output.startswith("```json"):
                        raw_output = raw_output[7:]
                    if raw_output.startswith("```"):
                        raw_output = raw_output[3:]
                    if raw_output.endswith("```"):
                        raw_output = raw_output[:-3]
                    
                    raw_output = raw_output.strip()
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
                
                df = pd.DataFrame(data_list)
                
                st.subheader("Daily Ledger")
                st.dataframe(df, use_container_width=True)
                
                if "Amount" in df.columns:
                    total = pd.to_numeric(df["Amount"], errors="coerce").sum()
                    st.metric(label="Total Tracked", value=f"KES {total:,.2f}")
                    
                    # CSV Export
                    csv_data = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Ledger as CSV",
                        data=csv_data,
                        file_name="mpesa_daily_ledger.csv",
                        mime="text/csv",
                    )
                
            except Exception as e:
                st.error(f"Error processing with {MODEL_PROVIDER}: {e}")
                if raw_output:
                    st.write("Raw AI Output received:", raw_output)
                    
    else:
        st.warning("Please paste some messages first.")