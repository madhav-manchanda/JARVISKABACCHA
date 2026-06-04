import requests
import time
import sys

BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "madhav@2006"

def test_login():
    print("Testing Login...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "username": USERNAME,
        "password": PASSWORD
    })
    
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
        
    data = resp.json()
    token = data.get("access_token")
    if not token:
        print("No access token received!")
        sys.exit(1)
        
    print("Login successful.")
    return token

def test_command(token):
    print("\nTesting Command/Text endpoint...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "text": "Send a text to Alex saying I'll be late by 10 minutes",
        "session_id": "test_script_01"
    }
    
    start_time = time.time()
    resp = requests.post(f"{BASE_URL}/command/text", json=payload, headers=headers)
    
    print(f"Response code: {resp.status_code}")
    print(f"Time taken: {time.time() - start_time:.2f}s")
    
    if resp.status_code != 200:
        print(f"Command failed: {resp.text}")
        sys.exit(1)
        
    print("Command response:")
    print(resp.json())

def test_health():
    print("\nTesting Health endpoint...")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"Health status: {resp.status_code}")
    print(resp.json())

if __name__ == "__main__":
    try:
        test_health()
        token = test_login()
        test_command(token)
        print("\nAll tests passed successfully!")
    except Exception as e:
        print(f"Test script error: {e}")
