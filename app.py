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

# --- External Pydantic Blueprint ---
class Transaction(BaseModel):
    Date: str
    Amount: int
    Entity: str
    Category: str

class Ledger(BaseModel):
    transactions: list[Transaction]

# --- Config & Initialization ---
load_dotenv()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "OLLAMA").upper()

st.set_page_config(page_title="Biashara Bookkeeper", page_icon="📊", layout="wide")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"**Active AI:** {MODEL_PROVIDER}\n\n*Change `MODEL_PROVIDER` in your `.env` to switch.*")
    st.markdown("---")
    st.markdown("### 💡 Tips")
    st.markdown("- Paste raw SMS text exactly as received.\n- The AI will automatically clean and categorize the data.")

# --- Main Header ---
st.title("📊 Biashara Bookkeeper")
st.markdown("Transform your raw M-Pesa messages into a structured financial ledger in seconds.")
st.divider()

# --- Application Layout (Tabs) ---
tab_ledger, tab_analytics = st.tabs(["📝 Data Entry & Ledger", "📈 Analytics Dashboard"])

with tab_ledger:
    # Use columns to put input on the left and results on the right
    col_input, col_results = st.columns([1, 2], gap="large")

    with col_input:
        st.subheader("1. Input Data")
        sms_input = st.text_area(
            "Paste M-Pesa SMS Receipts:", 
            height=300, 
            placeholder="Ksh1,500.00 paid to QUICKMART SUPERMARKET on 27/9/26..."
        )
        submit_btn = st.button("Process Receipts 🚀", type="primary", use_container_width=True)

    with col_results:
        st.subheader("2. Generated Ledger")
        
        if submit_btn:
            if not sms_input.strip():
                st.warning("⚠️ Please paste some messages first.")
            else:
                with st.spinner(f"AI ({MODEL_PROVIDER}) is analyzing your transactions..."):
                    
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
                        # --- AI Routing ---
                        if MODEL_PROVIDER == "NVIDIA":
                            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"))
                            response = client.chat.completions.create(
                                model="meta/llama3-70b-instruct",
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.1
                            )
                            raw_output = response.choices[0].message.content
                            
                        elif MODEL_PROVIDER == "GEMINI":
                            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
                            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                            raw_output = response.text
                            
                        elif MODEL_PROVIDER == "OLLAMA":
                            local_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
                            response = ollama.chat(
                                model=local_model, 
                                messages=[{'role': 'user', 'content': prompt}],
                                format=Ledger.model_json_schema()
                            )
                            raw_output = response['message']['content']

                        # --- Parse Output ---
                        if MODEL_PROVIDER == "OLLAMA":
                            parsed = json.loads(raw_output)
                            data_list = parsed.get("transactions", [])
                        else:
                            raw_output = raw_output.strip()
                            if raw_output.startswith("```json"): raw_output = raw_output[7:]
                            if raw_output.startswith("```"): raw_output = raw_output[3:]
                            if raw_output.endswith("```"): raw_output = raw_output[:-3]
                            
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
                        
                        # --- Render Dashboard ---
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        
                        if "Amount" in df.columns:
                            total = pd.to_numeric(df["Amount"], errors="coerce").sum()
                            
                            # Metrics and Download row
                            m_col1, m_col2 = st.columns(2)
                            m_col1.metric(label="Total Tracked Amount", value=f"KES {total:,.2f}")
                            
                            csv_data = df.to_csv(index=False).encode('utf-8')
                            m_col2.download_button(
                                label="📥 Download CSV",
                                data=csv_data,
                                file_name="mpesa_daily_ledger.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        
                        # Hide raw debug data in an expander to keep UI clean
                        with st.expander("🛠️ View Raw AI Output"):
                            st.code(raw_output, language="json")
                        
                    except Exception as e:
                        st.error(f"Processing Error: {e}")
                        with st.expander("View Raw Output for Debugging"):
                            st.write(raw_output)
        else:
            st.info("Awaiting input. Paste your messages on the left and click Process.")

with tab_analytics:
    st.title("Business Insights")
    st.info("🚧 Teammates: Build out charts, graphs, and expense pie-charts in this tab!")