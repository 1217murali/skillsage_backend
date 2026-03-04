import os
import sys
import django
from django.conf import settings
from decouple import config

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skillsageai.settings')
django.setup()

from openai import OpenAI
import traceback

def test_openrouter():
    print("\n--- Testing OpenRouter API ---")
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set in settings.")
        return False
    
    print(f"API Key found (starts with): {api_key[:5]}...")
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    

    models = [
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "google/gemini-2.0-pro-exp-02-05:free",
        "google/gemini-2.0-flash-thinking-exp:free",
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-chat:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
    ]
    
    for model in models:
        print(f"\nTesting model: {model}")
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello"}],
            )
            print(f"SUCCESS with {model}!")
            print(response.choices[0].message.content)
            return True
        except Exception as e:
            print(f"FAILED with {model}")
            print(e)
    
    return False


if __name__ == "__main__":
    test_openrouter()
