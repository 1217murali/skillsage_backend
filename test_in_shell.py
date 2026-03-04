import requests
import socket

print(f"DNS Resolution: {socket.gethostbyname('generativelanguage.googleapis.com')}")
try:
    print("Testing connection to generativelanguage.googleapis.com...")
    response = requests.get("https://generativelanguage.googleapis.com", timeout=10)
    print(f"Status: {response.status_code}")
except Exception as e:
    print(f"Error: {e}")
