from fastapi import FastAPI
from dotenv import load_dotenv

# Import the modular routers
from routers.whatsapp import router as whatsapp_router
from routers.integrations import router as integrations_router

load_dotenv()

app = FastAPI(
    title="Biashara Bookkeeper API",
    description="Automated M-Pesa ingestion and WhatsApp Conversational AI Bot"
)

# Connect the endpoints to the main app
app.include_router(whatsapp_router)
app.include_router(integrations_router)