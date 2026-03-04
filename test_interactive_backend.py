import requests
import json

BASE_URL = "http://127.0.0.1:8000"

# 1. Login to get token
def login():
    print("Logging in...")
    # Assuming a test user exists or we can use existing credentials
    # I'll try with a standard test user if I know one, or register one.
    # checking previous conversations/files might reveal a test user.
    import uuid
    random_id = str(uuid.uuid4())[:8]
    email = f"test_interactive_{random_id}@example.com"
    username = email
    password = "testpassword123"
    
    # Register first just in case
    print(f"Registering user: {email}")
    reg_response = requests.post(f"{BASE_URL}/register/", json={
        "username": username,
        "email": email,
        "password": password,
        "first_name": "Test",
        "last_name": "User"
    })
    print(f"Registration Status: {reg_response.status_code}")
    if reg_response.status_code != 201:
        print(f"Registration Response: {reg_response.text}")
    
    response = requests.post(f"{BASE_URL}/login/", json={
        "username": email,
        "email": email,
        "password": password
    })
    
    if response.status_code == 200:
        return response.json()['access']
    else:
        print(f"Login failed: {response.text}")
        return None

def test_interview_flow(token):
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Start Interview
    print("Starting interview...")
    response = requests.post(f"{BASE_URL}/api/start-interview/", headers=headers, json={
        "course": "Python Basics",
        "difficulty": "Easy"
    })
    
    if response.status_code != 201:
        print(f"Start interview failed: {response.text}")
        return
        
    data = response.json()
    session_id = data['session_id']
    questions = data['questions']
    first_question = questions[0]
    print(f"Session ID: {session_id}")
    print(f"Question 1: {first_question['question']}")
    
    # 3. Submit Answer
    print("Submitting answer...")
    answer_payload = {
        "session_id": session_id,
        "order_id": first_question['order'],
        "answer_text": "Python is a high-level programming language known for its readability. It uses indentation for code blocks.",
        "time_taken": 10
    }
    
    # We use multipart/form-data usually in frontend but JSON works if view handles it?
    # View uses `request.data.get`. DRF handles both if content-type is correct.
    # The frontend uses FormData. backend view `submit_answer` uses `request.data`.
    # Let's use requests.post with data/files to simulate FormData or just json if DRF parser is set.
    # The view `submit_answer` gets `answer_text` from `request.data`.
    
    response = requests.post(f"{BASE_URL}/submit_answer/", headers=headers, data=answer_payload)
    
    if response.status_code == 201:
        result = response.json()
        print("\n--- Response Data ---")
        print(json.dumps(result, indent=2))
        
        if "conversational_response" in result:
            print("\n✅ PASSED: 'conversational_response' field found.")
        else:
            print("\n❌ FAILED: 'conversational_response' field MISSING.")
    else:
        print(f"Submit answer failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    token = login()
    if token:
        test_interview_flow(token)
