import re

def analyze_mpesa_fraud(sms_text: str) -> dict:
    """
    Scans raw SMS text for common indicators of fake M-Pesa messages and scams.
    Returns a dictionary with 'is_suspicious' (bool) and 'reason' (str).
    """
    text_lower = sms_text.lower()

    # Rule 1: Check for unauthorized external links (Real M-Pesa never asks you to click links)
    link_patterns = ["http://", "https://", "bit.ly", "tinyurl", "www."]
    for link in link_patterns:
        if link in text_lower:
            return {
                "is_suspicious": True,
                "reason": f"Warning: Contains an external web link ('{link}'). Real M-Pesa messages never contain clickable links to claim money."
            }

    # Rule 2: Check for suspicious keywords related to fake winnings or promotions
    scam_keywords = ["won", "congratulations", "bonus", "free", "award", "mpesa express", "safcom promotion"]
    for keyword in scam_keywords:
        if keyword in text_lower:
            # Check if it looks like a standard business payment vs a promotion scam
            if "paid to" not in text_lower and "received from" not in text_lower:
                return {
                    "is_suspicious": True,
                    "reason": f"Warning: Contains promotional/lottery language ('{keyword}'). This is a common indicator of a phishing scam."
                }

    # Rule 3: Check for standard transaction code format
    if "confirmed" not in text_lower and "sent to" not in text_lower and "paid to" not in text_lower:
        if len(sms_text.strip()) > 10:
            return {
                "is_suspicious": True,
                "reason": "Notice: Missing standard Safaricom confirmation syntax ('Confirmed', 'paid to', or 'sent to')."
            }

    # If it passes basic checks
    return {
        "is_suspicious": False,
        "reason": "Message structure matches expected M-Pesa receipt formats."
    }