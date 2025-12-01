import requests
import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent 
DOTENV_PATH = BASE_DIR / ".env"
 
# Load the .env file from the root directory
load_dotenv(dotenv_path=DOTENV_PATH) 

BREVO_API_KEY = os.getenv("BREVO_API_KEY")

def send_email(to_email: str, subject: str, body: str) -> dict:
    """
    Sends an email using the Brevo (Sendinblue) API.

    Args:
        to_email: The recipient's email address.
        subject: The subject line of the email.
        body: The HTML content body of the email.

    Returns:
        A dictionary containing the HTTP status code and the Brevo API JSON response.
    """
    if not BREVO_API_KEY:
        print("ERROR: BREVO_API_KEY is not set.")
        return {"status_code": 500, "response": {"message": "API Key missing"}}
        
    url = "https://api.brevo.com/v3/smtp/email"
    
    payload = {
        "sender": {"name": "FamFin App", "email": "famfinapp579@gmail.com"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p>"
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        # --- CRITICAL TROUBLESHOOTING OUTPUT ---
        print("-" * 50)
        print(f"Brevo API Request Status Code: {response.status_code}")
        # ---------------------------------------

        try:
            response_json = response.json()
            if response.status_code not in (200, 201):
                 # Log the error details received from Brevo
                print(f"Brevo API Error Response: {response_json}")
            
        except requests.exceptions.JSONDecodeError:
            # Handle cases where Brevo returns a non-JSON error (rare)
            response_json = {"message": response.text}
            if response.status_code not in (200, 201):
                 print(f"Brevo API Non-JSON Error: {response.text}")

        return {
            "status_code": response.status_code,
            "response": response_json
        }
    
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to connect to Brevo API: {e}")
        return {"status_code": 503, "response": {"message": f"Connection error: {e}"}}

# --- Example Usage (Add this to your main script for testing) ---
# if __name__ == "__main__":
#     # NOTE: Replace with a real email for testing
#     test_result = send_email(
#         to_email="test@example.com", 
#         subject="Test Verification Code", 
#         body="Your code is 123456"
#     )
#     print("-" * 50)
#     print(f"Final Result: {test_result}")
#     if test_result.get('status_code') == 201:
#         print("SUCCESS: Email request accepted by Brevo.")
#     else:
#         print("FAILURE: Check Brevo logs and API Key.")