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
    
    def get_payment_methods(self):
        try:
            token = self.get_token()
            url = f"{self.BASE_URL}/get-vaultspay-allowed-payment-methods"
            headers = {
                "accessToken": token
            }
            data = {
                "currencyCode": "aed",
                "channelName": "web"
            }
            response = requests.post(url, data=data, headers=headers)
            if response.status_code != 200:
                raise Exception("VaultsPay API failed")
            raw = response.json()
            for item in raw.get("data", []):
                if item.get("name") in ["Visa/Master TEST", "Visa/Master"]:
                    return {
                        "status": "success",
                        "method_code": item.get("code")
                    }

            return {
                "status": "error",
                "message": "Visa/Master method not found"
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
        
    def initiate_payment(self, amount):
        try:
            #  Step 1: Get token
            token = self.get_token()
            #  Step 2: Get method code (SCM_01)
            method_data = self.get_payment_methods()
            if method_data["status"] != "success":
                raise Exception("Method code not found")
            method_code = method_data["method_code"]
            #  Step 3: Call initialize payment API
            url = f"{self.BASE_URL}/initialize-merchant-payment"
            headers = {
                "accessToken": token
            }
            data = {
                "amount": str(amount),
                "expiryInSeconds": "0",
                "schemaCode": method_code,   #  IMPORTANT
                "channelName": "web"
            }
            response = requests.post(url, data=data, headers=headers)
            if response.status_code != 200:
                raise Exception("Payment initialization failed")
            result = response.json()
            return {
                "status": "success",
                "payment_url": result["data"]["paymentUrl"],
                "payment_id": result["data"]["paymentId"]
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
        
        
    def verify_payment(self, payment_id):
        token = self.get_token()
        url = f"{self.BASE_URL}/get-merchant-payment-details"
        headers = {
            "accessToken": token
        }
        data = {
            "paymentId": payment_id
        }
        response = requests.post(url, data=data, headers=headers)
        result = response.json()
        #  Adjust based on real response
        if result.get("data", {}).get("status") == "success":
            return {"status": "success"}
        return {"status": "failed"}