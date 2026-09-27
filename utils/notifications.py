"""
WhatsApp notification helper using Twilio's WhatsApp API.
Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM in .env.
"""
import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox default


def send_whatsapp_welcome(name: str, phone: str) -> tuple[bool, str]:
    """Sends a welcome confirmation on WhatsApp after registration.
    phone must be in 2547XXXXXXXX format (as produced by auth._clean_phone).
    Never raises -- failures are logged and returned, so registration
    itself never breaks because of a notification hiccup."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return False, "WhatsApp notifications not configured (missing Twilio credentials)."

    to_number = f"whatsapp:+{phone}"

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=to_number,
            body=(
                f"Hello {name}, welcome to Biashara Bookkeeper! "
                "Your account has been created successfully. "
                "You can now log in and start tracking your M-Pesa transactions."
            ),
        )
        return True, "WhatsApp confirmation sent."
    except TwilioRestException as e:
        return False, f"Could not send WhatsApp message: {e.msg}"
    except Exception as e:
        return False, f"Could not send WhatsApp message: {e}"