import requests
import json

# Replace with your actual local or deployed Render/Koyeb URL
# Example Local: "http://127.0.0.1:8000/api/v1/telemetry"
# Example Cloud: "https://your-psars-api.onrender.com/api/v1/telemetry"
API_URL = "http://127.0.0.1:8000/api/v1/telemetry"

def send_test_telemetry(device_id: str, lat: float, lng: float, is_panic: bool, battery: float):
    # 1. Construct the payload matching your Pydantic schema
    payload = {
        "device_id": device_id,
        "latitude": lat,
        "longitude": lng,
        "panic": is_panic,
        "battery": battery
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    print(f"Sending payload to {API_URL}...")
    
    try:
        # 2. Make the HTTP POST request
        response = requests.post(API_URL, data=json.dumps(payload), headers=headers, timeout=10)
        
        # 3. Output results
        print(f"Status Code: {response.status_code}")
        print("Response Body:", response.json())
        
    except requests.exceptions.RequestException as e:
        print(f"Error sending request: {e}")

if __name__ == "__main__":
    # Test Normal GPS Ping
    print("--- Test 1: Regular Telemetry Update ---")
    send_test_telemetry(
        device_id="psars_node_01", 
        lat=7.377541, 
        lng=3.947022, 
        is_panic=False, 
        battery=92.0
    )

    print("\n--- Test 2: Emergency Panic Alert ---")
    # Test Panic Button Activation (Triggers FCM Push Notification)
    send_test_telemetry(
        device_id="psars_node_01", 
        lat=7.378110, 
        lng=3.948500, 
        is_panic=True, 
        battery=91.5
    )
