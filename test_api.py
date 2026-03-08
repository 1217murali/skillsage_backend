import os
import sys
import django
import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skillsageai.settings')
django.setup()

from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

def test_api():
    User = get_user_model()
    user = User.objects.first()
    if not user:
        print("No users in DB to test with")
        return
        
    token = str(RefreshToken.for_user(user).access_token)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get("http://localhost:8000/quiz/adaptive/?module_id=m-101&limit=5", headers=headers)
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.json())

if __name__ == "__main__":
    test_api()
