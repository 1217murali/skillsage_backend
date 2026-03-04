import os
import sys
import requests
import json
from decouple import config

# Mock settings since we are running standalone
try:
    from django.conf import settings
    # This might fail if django setup isn't done, but we'll try to read env vars directly
except:
    pass

def test_gemini_interview():
    print("\n--- Testing Gemini API for Interview Questions ---")
    
    # Try to get key from env
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            from decouple import Config, RepositoryEnv
            env_config = Config(RepositoryEnv(".env"))
            api_key = env_config("GEMINI_API_KEY")
        except:
            pass
            
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        return

    model = "gemini-flash-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    course = "React.js"
    difficulty = "Medium"
    prompt = f"""
    Generate interview questions for course: {course}, difficulty: {difficulty}.
    Total interview time: 25 minutes.
    Output strictly as JSON array only. Example:
    [
      {{"order": 1, "question": "Explain ...", "allocated_time": 120}}
    ]
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Success! Response:")
            data = response.json()
            text = data['candidates'][0]['content']['parts'][0]['text']
            print(text)
            return True
        else:
            print("Failed.")
            print(response.text)
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_gemini_interview()
