import requests
import time

class VaultsPayService:
    
    BASE_URL = "https://testapi.vaultspay.com/public/external/v1"
    
    def __init__(self):
        self.client_id = "ID-4564629946"
        self.client_secret = "SECRET-A17238A7-7568-48F4-94C1-98EA73AB9F65"
        
        self.access_token = None
        self.token_expiry_time = 0

    def get_token(self):
        # 🔁 reuse token if not expired
        if self.access_token and time.time() < self.token_expiry_time:
            return self.access_token

        url = f"{self.BASE_URL}/merchant-auth"

        response = requests.post(
            url,
            data={
                "clientId": self.client_id,
                "clientSecret": self.client_secret
            }
        )

        data = response.json()

        if response.status_code != 200:
            raise Exception("VaultsPay Auth Failed")

        token = data["data"]["access_token"]
        expiry = data["data"]["token_expiry"]

        # ⏱️ store token with expiry buffer
        self.access_token = token
        self.token_expiry_time = time.time() + expiry - 30  # buffer

        return token