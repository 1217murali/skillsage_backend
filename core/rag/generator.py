import requests
import os

GEMINI_API_KEY = os.getenv("AIzaSyDEV4I8_gmbwDN2eMfdHd_xBQaLzZ-oUoE")
''' genai.configure(api_key="AIzaSyD54U-jTwxNSIlit3Yd33Hu0s0H9PKJuIw")
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
