from fastapi import FastAPI
from dotenv import load_dotenv

# Must run BEFORE the routers are imported: they read MODEL_PROVIDER at import time,
# so loading .env afterwards silently left the API on the OLLAMA default.
load_dotenv()

# Import the modular routers
from routers.whatsapp import router as whatsapp_router
from routers.integrations import router as integrations_router

app = FastAPI(
    title="Biashara Bookkeeper API",
    description="Automated M-Pesa ingestion and WhatsApp Conversational AI Bot"
)

# Connect the endpoints to the main app
app.include_router(whatsapp_router)
app.include_router(integrations_router)