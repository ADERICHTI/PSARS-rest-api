import os
import requests
import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, messaging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional

load_dotenv()

# 1. Initialize Firebase Admin SDK
cred = credentials.Certificate("service-account-key.json")
firebase_admin.initialize_app(cred)

db = firestore.client()
app = FastAPI(title="PSARS Backend API")

# Termii Configuration (Recommend storing keys in environment variables)
TERMII_API_KEY = os.getenv("TERMII_API_KEY")
TERMII_URL = "https://v4.api.termii.com/api/sms/send"

# Helper Function: Termii SMS Gateway Dispatch
def send_termii_sms(to_phone: str, latitude: float, longitude: float):
    payload = {
        "api_key": TERMII_API_KEY,
        "to": to_phone,  # Format: "2348012345678"
        "from": "Termii",
        "sms": f"🚨 EMERGENCY: PSARS Panic Alert! Live location: https://maps.google.com/?q={latitude},{longitude}",
        "type": "plain",
        "channel": "generic"  # Guaranteed delivery across DND restrictions
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(TERMII_URL, json=payload, headers=headers, timeout=10)
        print(f"Termii SMS Response: {response.json()}")
        return response.json()
    except Exception as e:
        print(f"Termii SMS dispatch failed: {e}")
        return None

# 2. Define Request Schema (Matches what ESP32 POSTs)
class TelemetryData(BaseModel):
    device_id: str
    latitude: float
    longitude: float
    panic: bool = False
    battery: Optional[float] = None

# 3. HTTP Route for Hardware Telemetry
@app.post("/api/v1/telemetry", status_code=status.HTTP_200_OK)
async def receive_telemetry(data: TelemetryData):
    try:
        payload = data.model_dump()
        payload["timestamp"] = firestore.SERVER_TIMESTAMP

        # Step A: Save log to Firestore for app map stream
        db.collection("devices").document(data.device_id).collection("locations").add(payload)
        
        # Update latest status on device document
        db.collection("devices").document(data.device_id).set(
            {"latest_location": payload, "last_seen": firestore.SERVER_TIMESTAMP}, 
            merge=True
        )

        # Step B: Trigger Panic Alerts (FCM + Termii) for every emergency contact
        if data.panic:
            device_doc = db.collection("devices").document(data.device_id).get()

            emergency_contacts = []
            if device_doc.exists:
                emergency_contacts = device_doc.to_dict().get("emergency_contacts", [])

            for contact in emergency_contacts:
                contact_name = contact.get("name", "contact")
                fcm_token = contact.get("fcm_token")
                phone_number = contact.get("phone_number")

                # 1. Dispatch FCM Push Notification (only if this contact has an account + token)
                if fcm_token:
                    try:
                        message = messaging.Message(
                            notification=messaging.Notification(
                                title="🚨 PSARS EMERGENCY ALERT",
                                body=f"Panic activated! Location: {data.latitude}, {data.longitude}",
                            ),
                            data={
                                "lat": str(data.latitude),
                                "lng": str(data.longitude),
                                "device_id": data.device_id,
                            },
                            token=fcm_token,
                            android=messaging.AndroidConfig(priority="high"),
                        )
                        messaging.send(message)
                        print(f"FCM alert sent to {contact_name}.")

                    except messaging.UnregisteredError:
                        print(f"Warning: FCM token for {contact_name} is expired or invalid.")
                    except Exception as e:
                        print(f"Failed to send FCM alert to {contact_name}: {e}")

                # 2. Dispatch Termii SMS (every contact has a phone number, account or not)
                if phone_number:
                    send_termii_sms(phone_number, data.latitude, data.longitude)

        return {"status": "success", "panic_triggered": data.panic}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))