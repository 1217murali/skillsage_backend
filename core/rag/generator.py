import requests
import os
import json
from dotenv import load_dotenv

# load environment variables from a .env file (if present)
load_dotenv()

# use a descriptive variable name for the env var
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set in the environment")

# legacy notes for reference (do not include actual keys in source)
''' genai.configure(api_key="<REDACTED>")
    model = genai.GenerativeModel("gemini-2.0-flash")'''
def generate_questions(course, difficulty, context_docs, total_duration=25):
    prompt = f"""
    You are an AI that generates interview questions for the course: {course}.
    Difficulty level: {difficulty}.
    Total interview time: {total_duration} minutes.

    Based on the context below, generate a list of interview questions.
    Each question must have:
    - The question text
    - Suggested time to answer (seconds)
    - Order number

    Context:
    {context_docs}

    Output as JSON array:
    [
      {{"order": 1, "question": "Explain stacks and queues.", "allocated_time": 120}},
      ...
    ]
    """

    # Example using Gemini or OpenAI
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateText",
        headers={"Authorization": f"Bearer {GEMINI_API_KEY}"},
        json={"contents": [{"parts": [{"text": prompt}]}]}
    )

    result = response.json()
    generated_text = result["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(generated_text)
