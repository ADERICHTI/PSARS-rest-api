import hashlib
import hmac
import os
import requests
import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, messaging
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from typing import Optional

load_dotenv()

# 1. Initialize Firebase Admin SDK.
# Locally, use the service account key file. In Cloud Run, no key file is
# shipped in the image at all - the service runs as an attached IAM service
# account, and firebase_admin.initialize_app() with no args picks that up
# automatically via Application Default Credentials.
if os.path.exists("service-account-key.json"):
    cred = credentials.Certificate("service-account-key.json")
    firebase_admin.initialize_app(cred)
else:
    firebase_admin.initialize_app()

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

# Per-device auth: each device's key is provisioned once (see
# provision_device.py) as a SHA-256 hash stored at
# devices/{device_id}/secrets/auth - a path with no firestore.rules match,
# so it's unreachable from any client, only from this backend via the admin
# SDK. The raw key itself is never stored anywhere - only its hash.
def verify_device_key(device_id: str, authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    provided_key = authorization.removeprefix("Bearer ").strip()

    secret_doc = (
        db.collection("devices").document(device_id).collection("secrets").document("auth").get()
    )
    if not secret_doc.exists:
        raise HTTPException(status_code=401, detail="Unknown or unprovisioned device")

    stored_hash = secret_doc.to_dict().get("api_key_hash", "")
    provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()

    if not hmac.compare_digest(provided_hash, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid device key")

# 3. HTTP Route for Hardware Telemetry
@app.post("/api/v1/telemetry", status_code=status.HTTP_200_OK)
async def receive_telemetry(data: TelemetryData, authorization: Optional[str] = Header(None)):
    # Runs before the try block below on purpose: HTTPException is a subclass
    # of Exception, so raising it inside that block would get caught by its
    # bare `except Exception` and rewritten into a misleading 500.
    verify_device_key(data.device_id, authorization)

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
            contacts_ref = db.collection("devices").document(data.device_id).collection("emergency_contacts")
            emergency_contacts = [doc.to_dict() for doc in contacts_ref.stream()]

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