# Biashara Bookkeeper

Biashara Bookkeeper is a Kenyan business finance and M-Pesa bookkeeping assistant built with Python, Streamlit, and FastAPI. It helps users capture M-Pesa SMS receipts, parse the transactions, detect suspicious or phishing messages, store book-keeping data, and visualize business performance in a dashboard.

The app is designed for small business owners who want to track income, expenses, and payment flow without manually entering every transaction.

## Features

- M-Pesa receipt parsing from pasted SMS or forwarded messages
- AI-assisted transaction extraction with fallback to a local rule-based parser
- Fraud/phishing detection for suspicious SMS content
- SQLite ledger database for transaction storage
- User authentication and registration for business accounts
- Financial dashboard with summary metrics and analytics
- WhatsApp/Twilio webhook integration for automated SMS ingestion
- Local language support and UI theming
- Voice recording support for incoming receipt descriptions

## Tech stack

- Python 3.10+
- Streamlit
- FastAPI
- SQLite
- PostgreSQL (for auth/user database)
- Pandas
- OpenAI / Gemini / NVIDIA / Ollama AI providers
- Twilio messaging integration

## Project structure

```text
biashara_app/
├── app.py                     # Main Streamlit UI
├── main_api.py               # FastAPI application entrypoint
├── database.py               # SQLite ledger and entity-memory logic
├── requirements.txt          # Python dependencies
├── .env.example              # Example environment file
├── .env                      # Local environment variables (not committed)
├── assets/
│   └── styles.css            # UI styling
├── components/
│   ├── metrics.py             # KPI cards
│   ├── sidebar.py            # Sidebar controls and filters
│   └── tabs.py               # Ledger and analytics tabs
├── localization/
│   └── translations.py       # Text and language mappings
├── routers/
│   ├── integrations.py       # Integration APIs, Daraja hooks
│   └── whatsapp.py           # WhatsApp webhook endpoint
├── utils/
│   ├── ai_router.py          # AI provider routing
│   ├── auth.py               # Login/register logic and PostgreSQL auth DB
│   ├── bot_helpers.py        # Shared WhatsApp helper functions
│   ├── fraud_detector.py     # Suspicious message detection
│   ├── ledger_ai.py          # Ledger Q&A AI logic
│   ├── parsing.py            # M-Pesa text parsing
│   ├── theme.py              # Theme logic
│   ├── voice.py              # Speech transcription helper
│   └── ...
├── sample_mpesa.txt          # Example SMS transactions
├── ledger.db                 # Local SQLite ledger database
└── README.md                 # Project documentation
```

## Prerequisites

Before running the project, make sure you have:

- Python 3.10 or newer
- pip
- virtual environment support
- PostgreSQL server if you want the auth system to work
- Optional: Ollama running locally for local AI parsing
- Optional: API keys for OpenAI, Gemini, or NVIDIA
- Optional: Twilio credentials if using the WhatsApp flow

## Environment variables

Copy the example file and update the values:

```powershell
copy .env.example .env
```

The app expects these values in `.env` (or in Streamlit secrets for `DATABASE_URL`):

| Variable         | Required          | Description                                            |
| ---------------- | ----------------- | ------------------------------------------------------ |
| `MODEL_PROVIDER` | Yes               | AI provider: `OLLAMA`, `OPENAI`, `GEMINI`, or `NVIDIA` |
| `OLLAMA_MODEL`   | Optional          | Local Ollama model name                                |
| `OPENAI_API_KEY` | Optional          | OpenAI API key                                         |
| `GEMINI_API_KEY` | Optional          | Google Gemini API key                                  |
| `DATABASE_URL`   | Required for auth | PostgreSQL connection string for user accounts         |
| `DB_PATH`        | Optional          | SQLite DB override for ledger storage                  |

Example:

```env
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your-key-here
OLLAMA_MODEL=llama3.2
MODEL_PROVIDER=ollama
DATABASE_URL=postgresql://user:password@host:5432/database
```

## Quick start

### 1) Clone and enter the project

```powershell
cd "C:\Users\USER\OneDrive\Desktop\biashara_app"
```

### 2) Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3) Install dependencies

```powershell
pip install -r requirements.txt
```

### 4) Configure environment variables

```powershell
copy .env.example .env
```

Then update the .env file with your own keys and database URL.

### 5) Start the Streamlit app

```powershell
streamlit run app.py
```

Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

### 6) Start the API server (optional)

```powershell
uvicorn main_api:app --host 0.0.0.0 --port 8000 --reload
```

This starts the FastAPI endpoints used by the WhatsApp bot and webhook integrations.

## Running the app in practice

### Streamlit dashboard

Use the dashboard to:

- log in or register an account
- paste M-Pesa screenshots or SMS text
- analyze transactions
- review ledger data and analytics
- switch AI providers
- manage theme and app settings

### WhatsApp / webhook flow

The project includes webhook logic for receiving WhatsApp or forwarded SMS messages. The router is mounted through `main_api.py` and includes endpoints such as:

- `/whatsapp`
- `/api/auto-receipt/sms`
- `/api/daraja/c2b/validation`
- `/api/daraja/c2b/confirmation`

These can be connected to Twilio or a custom gateway to ingest incoming M-Pesa messages automatically.

## How the app works

1. A user pastes or forwards an M-Pesa SMS.
2. The message is checked for phishing or suspicious content.
3. The app identifies whether it looks like a valid transaction.
4. A parser extracts:
   - transaction code
   - date
   - entity
   - type (income or expense)
   - amount
   - category
   - channel
5. The app saves the data to SQLite.
6. The dashboard aggregates and displays the business ledger.
7. The system learns categories from prior entity names and reuses them.

## Authentication and user data

The app uses a PostgreSQL-backed auth database for user accounts via `utils/auth.py`.

User accounts store:

- full name
- email
- phone number
- account type (`Till` or `Paybill`)
- account number
- password hash and salt

This is separate from the SQLite ledger used for transactions. The login flow is session-based in Streamlit.

## Database behavior

### Ledger database

The ledger is stored in SQLite with a table named `transactions` and entity memory in `entity_memory`.

At a high level, the transaction schema includes:

- `Transaction Code`
- `Date`
- `Entity`
- `Type`
- `Amount (KES)`
- `Category`
- `Channel`
- `user_id`

This supports per-user ledger separation and duplicate-safe inserts.

## AI processing

The app currently supports the following AI providers:

- Ollama (local model)
- OpenAI
- Google Gemini
- NVIDIA

The provider is selected from the sidebar and passed through the router in `utils/ai_router.py`.

If the AI call fails or returns unusable data, the code falls back to the built-in parser in `utils/parsing.py`.

## Troubleshooting

### Streamlit fails to start

Check that:

- the environment is active
- required packages are installed
- `.env` or secrets contain the required values

```powershell
pip install -r requirements.txt
streamlit run app.py
```

### Auth fails because `DATABASE_URL` is missing

Set `DATABASE_URL` in `.env`, or add it under the Streamlit secrets config.

### OpenAI/Gemini/Ollama not working

Verify that:

- the API key is configured correctly
- `MODEL_PROVIDER` matches the selected provider
- the Ollama service is running locally if using Ollama

### Duplicate transactions appearing

The app uses transaction codes to prevent re-inserting the same transaction. If duplicates appear, check whether your DB was initialized correctly or whether the same message is being processed twice.

## Security notes

- The app blocks suspicious and phishing-like M-Pesa text before saving transactions.
- Passwords are hashed using PBKDF2-HMAC-SHA256.
- Do not commit your `.env` file to source control.
- Keep API keys and production credentials in a secure environment.

## Example usage

A user can paste a message like this:

```text
QJH7XK2P
Received Ksh 1,200.00 from Jane Wanjiku 0712345678 on 20/11/26
```

The app will:

- identify it as an income transaction
- parse the amount and sender
- classify or remember the entity
- save it to the ledger
- show it in the dashboard metrics and table

## License

This project currently does not include a formal license declaration. If you plan to share or distribute it publicly, add an appropriate open-source license such as MIT or Apache 2.0.

## Recommended next step

If you want to build this further, the strongest next improvements are:

1. add a proper database migration system
2. unify the auth DB and ledger DB approach
3. add automated tests for parsing and fraud detection
4. document the Twilio/WhatsApp webhook setup end-to-end
5. add deployment config for Docker or cloud hosting

## Contributing

Pull requests and improvements are welcome. Keep the code modular and testable, and document any new providers, API routes, or database schema changes.
