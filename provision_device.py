"""
Provisions a device's auth key. Run this once per physical unit.

Generates a random secret, stores only its SHA-256 hash in Firestore at
devices/{device_id}/secrets/auth (a path with no firestore.rules match, so
no client can ever read it - only this backend, via the admin SDK), and
prints the raw secret exactly once. That raw value is what gets handed to
whoever flashes the device - it is never written anywhere else.

Usage:
    python provision_device.py psars_node_01
"""

import hashlib
import secrets
import sys

import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("service-account-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()


def provision(device_id: str) -> str:
    raw_key = secrets.token_hex(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    db.collection("devices").document(device_id).collection("secrets").document("auth").set(
        {"api_key_hash": key_hash}
    )

    return raw_key


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python provision_device.py <device_id>")
        sys.exit(1)

    device_id = sys.argv[1]
    raw_key = provision(device_id)

    print(f"Provisioned '{device_id}'.")
    print("Give this raw key to whoever flashes the device - it will not be shown again:")
    print(raw_key)
