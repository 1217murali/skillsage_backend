import requests
import os
import socket

print(f"DNS Resolution for generativelanguage.googleapis.com: {socket.gethostbyname('generativelanguage.googleapis.com')}")

try:
    response = requests.get("https://generativelanguage.googleapis.com", timeout=10)
    print(f"Status Code: {response.status_code}")
except Exception as e:
    print(f"Error: {e}")

print("Environment Variables:")
for k, v in os.environ.items():
    if "PROXY" in k.upper():
        print(f"{k}: {v}")
