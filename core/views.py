import io
import os
import json
import re
import traceback
try:
    import requests
except ImportError:
    requests = None
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
try:
    import numpy as np
except ImportError:
    np = None
try:
    from scipy.io import wavfile
except ImportError:
    wavfile = None
try:
    import whisper
except ImportError:
    whisper = None
try:
    import librosa
except ImportError:
    librosa = None
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.core.mail import send_mail
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.dateformat import format
from django.db import transaction
from django.db.models import Count, Q, F
from django.db.models.functions import TruncMonth

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.generics import RetrieveUpdateAPIView

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from openai import OpenAI

from .models import (
    AppUser, PasswordResetToken, Profile, InterviewSession, 
    InterviewQuestion, InterviewAnswer, Resume, CourseProgress, 
    DailyCount, KnowledgePoint
)
from .serializers import RegisterSerializer, ProfileSerializer
from .rag.vectorstore import VectorStoreChroma
from .rag.scraper import fetch_online_course_data

# Initialize Global Objects
User = get_user_model()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY
)

# Global cache for documents (legacy)
documents = []

try:
    # Use 'base' for a good balance of speed and accuracy
    whisper_model = whisper.load_model("small")
except Exception as e:
    print(f"CRITICAL: Failed to load Whisper model: {e}")
    whisper_model = None

# Helper Functions
def extract_json_from_text(text):
    try:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match: return json.loads(match.group(1))
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match: return json.loads(match.group(1))
        return json.loads(text.strip())
    except (json.JSONDecodeError, AttributeError):
        return None


class GoogleLoginAPIView(APIView):
    def post(self, request):
        token = request.data.get('token')
        try:
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), settings.GOOGLE_CLIENT_ID)
            email = idinfo['email']
            name = idinfo.get('name', 'No Name')
            user, created = AppUser.objects.get_or_create(email=email, defaults={
                'username': email.split('@')[0],
                'login_method': 'google',
            })
            token, _ = Token.objects.get_or_create(user=user)
            return Response({'token': token.key, 'user': {'email': user.email, 'name': name}})
        except ValueError:
            return Response({'error': 'Invalid token'}, status=400)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "User created successfully",
                "redirect_url": "http://localhost:5173/login"
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class CustomLoginView(TokenObtainPairView):
    serializer_class = TokenObtainPairSerializer



@csrf_exempt
def request_password_reset(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get("email")
    except:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({"detail": "If user exists, email will be sent."}, status=200)

    token_obj = PasswordResetToken.objects.create(user=user)
    reset_link = f"http://127.0.0.1:8000/password-reset-confirm/{token_obj.token}/"

    # Send email
    send_mail(
        subject="Reset Your Password – SkillSageAi",
        message=f"""
Hello from SkillSageAi!

You're receiving this email because you (or someone else) requested a password reset for your account.

If you did not request this, you can safely ignore this email.

To reset your password, click the link below:

{reset_link}

This link will expire in 1 hour for your security.

Thanks,
The SkillSageAi Team
""",
        from_email="no-reply@example.com",
        recipient_list=[user.email],
        fail_silently=False,
    )

    return JsonResponse({"detail": "If user exists, email will be sent."}, status=200)




def clean_expired_tokens():
    expired_tokens = PasswordResetToken.objects.all()
    deleted_count = 0

    for token in expired_tokens:
        if token.is_expired():
            token.delete()
            deleted_count += 1

    return deleted_count
 
def password_reset_confirm(request, token):
    try:
        count1= clean_expired_tokens()
        print(f"Cleaned {count1} expired tokens.")
        reset_token = PasswordResetToken.objects.get(token=token)
    except PasswordResetToken.DoesNotExist:
        return render(request, "core/password_reset_form.html", {"error": "Invalid reset link."})

    if reset_token.is_expired():
        reset_token.delete()
        return render(request, "core/password_reset_form.html", {"error": "Link expired. Please request again."})

    if request.method == "POST":
        password1 = request.POST.get("new_password1")
        password2 = request.POST.get("new_password2")

        if not password1 or not password2:
            return render(request, "core/password_reset_form.html", {"error": "Both fields are required."})

        if password1 != password2:
            return render(request, "core/password_reset_form.html", {"error": "Passwords do not match."})

        reset_token.user.password = make_password(password1)
        reset_token.user.save()
        reset_token.delete()

        return redirect("http://localhost:5173/login")

    return render(request, "core/password_reset_form.html")


class SomeProtectedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": "secret data"})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)



def google_login_token_view(request):
    user = request.user
    if user.is_authenticated:
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        # Pass the tokens to frontend via URL
        frontend_url = f"http://localhost:5173/google-auth?access={access_token}&refresh={refresh_token}"
        return redirect(frontend_url)
    return redirect("http://localhost:5173/login")


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
        })


class ProfileView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user.profile


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }



@csrf_exempt
def upload_to_imgur(image_file):
    """
    Uploads an image file to Imgur and returns the public URL.
    """
    url = "https://api.imgur.com/3/image"
    headers = {
        "Authorization": f"Client-ID {settings.IMGUR_CLIENT_ID}"
    }

    try:
        # Upload image to Imgur
        response = requests.post(url, headers=headers, files={"image": image_file})
        print(response.status_code)
        response.raise_for_status()  # Will raise an HTTPError if the status code is not 2xx

        # Parse the response
        response_data = response.json()
        print(response_data)
        if response_data.get('success'):
            return response_data['data']['link']  # Return the public image URL
        else:
            raise Exception("Imgur API response indicates failure.")
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to upload image to Imgur: {str(e)}")




class UploadProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file = request.FILES.get("image")
        if not file:
            return Response({"error": "No image uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            profile, _ = Profile.objects.get_or_create(user=request.user)
            imgur_url = upload_to_imgur(file)
            profile.profile_image = imgur_url
            profile.save()

            return Response({"profile_image": imgur_url}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_email(request):
    return Response({
        "email": request.user.email,
        "login_method": request.user.login_method
    })




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_interview(request):
    user = request.user
    course = request.data.get("course")
    difficulty = request.data.get("difficulty")

    if not course or not difficulty:
        return Response({"error": "course and difficulty required"}, status=400)

    # --- 1. Initialize Chroma vector store ---
    vs = VectorStoreChroma()

    # --- 2. Search existing documents ---
    raw_results = vs.search(query=course, top_k=10, course=course, difficulty=difficulty)
    results = [doc for doc in raw_results if doc.metadata.get("difficulty") == difficulty]
    print("Raw results:", raw_results)

    # --- 3. Fetch online sources if no relevant documents ---
    if not raw_results:
        new_docs, metadatas = fetch_online_course_data(course, difficulty)
        print("New docs:", new_docs)
        print("Metadatas:", metadatas)
        if new_docs:
            vs.build_index(new_docs, metadatas)
            documents.extend([{
                "page_content": doc,
                "metadata": meta
            } for doc, meta in zip(new_docs, metadatas)])

            # Search again after adding
            raw_results = vs.search(query=course, top_k=10, course=course, difficulty=difficulty)
            results = [doc for doc in raw_results if doc.metadata.get("difficulty") == difficulty]

    # --- 4. Prepare context for LLM ---
    # Truncate context to prevent token limits
    MAX_CONTEXT_LEN = 8000
    full_context = "\n".join([doc.page_content for doc in results]) if results else "No relevant documents found."
    if len(full_context) > MAX_CONTEXT_LEN:
        full_context = full_context[:MAX_CONTEXT_LEN] + "...(truncated)"
    
    print(f"Context length: {len(full_context)}")

    # Determine question count based on difficulty
    difficulty_lower = difficulty.lower()
    if difficulty_lower == "medium":
        num_questions = 10
    elif difficulty_lower == "hard":
        num_questions = 15
    else:  # "easy" or default
        num_questions = 5

    total_time = num_questions  # 1 minute per question

    prompt = f"""
Generate {num_questions} interview questions for course: {course}, difficulty: {difficulty}.
Total interview time: {total_time} minutes.
The allocated time for each question should be exactly 60 seconds (1 minute).

The questions should be interview-style, considering online context and generalized course-related topics.
Do not include introductory text, just the {num_questions} questions in JSON format.
Context:
{full_context}

Output strictly as JSON array only. Example:
[
  {{"order": 1, "question": "Explain ...", "allocated_time": 60}}
]
"""

    # --- 5. Generate questions via Google Gemini API ---
    try:
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        # Increased timeout for generation
        response = requests.post(gemini_url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
             print(f"Gemini API Error: {response.text}") # Log query error
             return Response({
                "error": "Gemini API failed",
                "details": response.text,
                "status_code": response.status_code
            }, status=502)

        data = response.json()
        try:
             generated_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
        except (KeyError, IndexError):
             return Response({
                "error": "Invalid response format from Gemini",
                "raw_response": data
            }, status=502)

        # --- Clean JSON from markdown or extra text ---
        # Robust cleaning for code blocks
        generated_text = re.sub(r"^```[a-zA-Z]*\n", "", generated_text)
        generated_text = re.sub(r"^```", "", generated_text)
        generated_text = re.sub(r"```$", "", generated_text)
        generated_text = generated_text.strip()

        # Extract JSON array if surrounded by text
        match = re.search(r"\[.*\]", generated_text, re.DOTALL)
        if match:
            generated_text = match.group(0)

        # Parse JSON safely
        questions = json.loads(generated_text)

    except json.JSONDecodeError as json_err:
        traceback.print_exc()
        return Response({
            "error": "LLM returned invalid JSON",
            "raw_text": generated_text,
            "details": str(json_err)
        }, status=500)

    except Exception as e:
        traceback.print_exc()
        return Response({
            "error": "Unexpected error during LLM call",
            "details": str(e)
        }, status=500)


    # --- 6. Save session and questions in DB ---
    session = InterviewSession.objects.create(user=user, course=course, difficulty=difficulty)
    for q in questions:
        InterviewQuestion.objects.create(
            session=session,
            question_text=q["question"],
            allocated_time=q["allocated_time"],
            order=q["order"]
        )
    name = user.get_full_name() or (user.username if user.username else "student")

    return Response({"session_id": session.id, "questions": questions,"username":name}, status=201)



def _transcribe_wav_file(audio_file):
    """
    Helper function to transcribe a WAV file using the Whisper model.
    Handles WAV read, mono conversion, normalization, and resampling to 16kHz.
    
    Returns: transcribed text (str) or an error string starting with "ERROR"
    """
    if not whisper_model:
        return "ERROR: Transcription model not loaded on server."

    try:
        # File is a Django UploadedFile, read its bytes
        wav_bytes = audio_file.read()

        samplerate, data = wavfile.read(io.BytesIO(wav_bytes))

        # Convert stereo to mono if needed
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        # Convert to float32 [-1.0, 1.0] and normalize
        audio = data.astype(np.float32)
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio /= max_val

        # Resample to 16kHz, which is required for Whisper
        audio_resampled = librosa.resample(audio, orig_sr=samplerate, target_sr=16000)
    
        # Transcribe
        result = whisper_model.transcribe(audio_resampled, language="en")
        print(result["text"])
        return result["text"].strip()

    except Exception as e:
        print(e)
        return f"ERROR: Audio processing failed: {type(e).__name__} - {str(e)}"

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_answer(request):
    """
    Submits an answer for a specific question.
    Handles both WAV file upload (transcribed by Whisper) and plain text (for skips/errors).
    """
    user = request.user
    session_id = request.data.get('session_id')
    order_id = request.data.get('order_id')
    time_taken = request.data.get('time_taken', 0)
    audio_file = request.FILES.get('answer_audio')
    print("Received data:", request.data)
    
    # 1. Start with the transcript being the text fallback or empty
    final_transcript = request.data.get('answer_text', "").strip()

    # 2. Validate essential data
    if not all([session_id, order_id]):
        return Response({"error": "Missing required fields: session_id and order_id."}, status=400)
    
    # 3. Handle Audio File Transcription
    if audio_file:
        # Only attempt transcription if the file is not empty (a skip/timeout can result in an empty file)
        if audio_file.size > 0:
            transcribed_text = _transcribe_wav_file(audio_file)
            
            # Check for error returned by the transcription helper
            if transcribed_text.startswith("ERROR"):
                final_transcript = transcribed_text
                # Log the error but continue to save the error message in the DB
                print(f"Transcription Error: {final_transcript}")
            else:
                final_transcript = transcribed_text
        else:
            final_transcript = "No audio recorded (empty file submitted)."

    # 4. Handle Text Fallback / Skips
    # If no file was provided and the fallback text is empty, set a default message.
    if not final_transcript:
        final_transcript = "No verbal answer provided (Text fallback used)."
        
    # The final text to be saved in the database
    answer_to_save = final_transcript
    
    # 5. Retrieve and Validate Session/Question
    try:
        session = get_object_or_404(InterviewSession, id=session_id, user=user)
    except Exception:
        return Response({"error": "Invalid session_id or session does not belong to user."}, status=404)

    try:
        # Retrieve the specific question using both the session and the order_id.
        question = get_object_or_404(InterviewQuestion, session=session, order=order_id)
    except Exception:
        return Response({"error": "Question not found for this session and order_id."}, status=404)

    # 6. Save the Answer
    answer, created = InterviewAnswer.objects.update_or_create(
        question=question,
        user=user,
        defaults={
            "answer_text": answer_to_save,
            "time_taken": time_taken,
            "submitted_at": timezone.now()
        }
    )

    # 7. Real-time Analysis via Gemini
    analysis_data = {
        "feedback": "Analysis not available.",
        "improvement_tip": "",
        "rating": 0
    }

    try:
        if answer_to_save and len(answer_to_save) > 5 and requests:
            prompt = f"""
            Analyze the following answer to the interview question: "{question.question_text}".
            
            Answer: "{answer_to_save}"
            
            Provide the output in strict JSON format:
            {{
                "feedback": "One short sentence evaluating the answer.",
                "improvement_tip": "One short, actionable tip to improve.",
                "rating": <integer between 1 and 5>,
                "conversational_response": "A short, natural, encouraging spoken response (1-2 sentences) reacting to the answer as if you are the interviewer face-to-face. Don't be too generic."
            }}
            """
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            
            response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=45)
            if response.status_code == 200:
                gemini_data = response.json()
                text_content = gemini_data['candidates'][0]['content']['parts'][0]['text']
                
                analysis_data = extract_json_from_text(text_content)
                if not analysis_data:
                     # Fallback if parsing fails
                     analysis_data = {
                        "feedback": "Feedback processing failed.",
                        "improvement_tip": "Keep practicing to improve.",
                        "rating": 3,
                        "conversational_response": "Thank you for your answer. Let's move to the next question."
                     }
            else:
                 analysis_data["feedback"] = f"Analysis unavailable (API Error: {response.status_code})"

    except Exception as e:
        print(f"Gemini Analysis Error: {e}")
        analysis_data["feedback"] = f"Analysis unavailable (Error: {str(e)})"
        analysis_data["conversational_response"] = "Thank you. Logic check: I encountered an error analyzing your answer, but it has been recorded."


    # 8. Progress Tracking
    total_questions = session.questions.count()
    answered_questions = InterviewAnswer.objects.filter(question__session=session, user=user).count()

    if answered_questions == total_questions:
        session.completed = True
        session.save()

    # 9. Return the final transcript + ANALYSIS to the frontend
    return Response({
        "message": "Answer saved and analyzed successfully.",
        "transcript": answer_to_save,
        "feedback": analysis_data.get("feedback"),
        "improvement_tip": analysis_data.get("improvement_tip"),
        "rating": analysis_data.get("rating"),
        "session_id": session.id,
        "answered_questions": answered_questions,
        "total_questions": total_questions,
        "completed": session.completed
    }, status=201)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_interview_summary(request):
    """
    Retrieves the interview summary by using the Gemini API.
    """
    user = request.user
    session_id = request.data.get('session_id')

    if not session_id:
        return Response({"error": "Missing required field: session_id."}, status=400)

    try:
        session = get_object_or_404(InterviewSession, id=session_id)
    except Exception:
        return Response({"error": "Invalid session_id."}, status=404)

    if session.user != user:
        return Response({"error": "You are not authorized to view this session summary."}, status=403)

    answers = InterviewAnswer.objects.filter(
        question__session=session,
        user=user
    ).order_by('question__order')
    
    if not answers.exists():
        return Response({"error": "No answers found for this session."}, status=404)

    prompt_parts = [
        "You are an AI interviewer. Instead of a text summary, provide a final 5-star rating assessment.",
        "Here are the user's answers:",
        ""
    ]
    
    for answer in answers:
        question_text = answer.question.question_text if hasattr(answer.question, 'question_text') else answer.question.question
        answer_text = answer.answer_text
        prompt_parts.append(f"Q: {question_text}")
        prompt_parts.append(f"A: {answer_text}")
        prompt_parts.append("")

    prompt_parts.append("""
    Based on the overall performance, provide a JSON output:
    {
        "average_rating": <float between 1.0 and 5.0>,
        "feedback": "One short, encouraging closing remark summarizing the user's performance.",
        "stars": "⭐⭐⭐",
        "spoken_rating": "3 out of 5 stars"
    }
    """)
        
    prompt = "\n".join(prompt_parts)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }
    
    if not requests:
         return Response({
            "average_rating": 4.0,
            "feedback": "Great job completing the interview! (Offline Mode)",
            "stars": "⭐⭐⭐⭐",
            "spoken_rating": "4 out of 5 stars"
        }, status=200)

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=45)
        
        if response.status_code != 200:
             return Response({
                "average_rating": 0,
                "feedback": f"Analysis failed (API Error: {response.status_code}). Good effort!",
                "stars": "⭐",
                "spoken_rating": "Interview completed with errors."
            }, status=200)
            
        gemini_response = response.json()
        try:
            text_content = gemini_response['candidates'][0]['content']['parts'][0]['text']
            summary_data = extract_json_from_text(text_content)
        except (KeyError, IndexError, TypeError):
             summary_data = None
        
        if not summary_data:
             summary_data = {
                "average_rating": 3.0,
                "feedback": "Interview completed. Formatting error in analysis.",
                "stars": "⭐⭐⭐"
             }

        return Response(summary_data, status=200)
        
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return Response({
            "average_rating": 3.0,
            "feedback": "Interview completed. (Network Error)",
            "stars": "⭐⭐⭐"
        }, status=200)

# NOTE: The original 'transcribe_audio' view has been removed as its functionality is now 
# integrated directly into 'submit_answer' via the '_transcribe_wav_file' helper function.


# Helper: extract resume details

# Helper: extract resume details
def extract_resume_details(pdf_path):
    doc = fitz.open(pdf_path)
    resume_data = {"pages": []}

    for page_num, page in enumerate(doc, start=1):
        page_data = {"page_number": page_num, "text": [], "images": []}
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" in b:
                for line in b["lines"]:
                    for span in line["spans"]:
                        page_data["text"].append({
                            "text": span["text"],
                            "font": span["font"],
                            "size": span["size"],
                            "color": span["color"],
                            "bbox": span["bbox"]
                        })
        resume_data["pages"].append(page_data)
    return resume_data


# Helper: call Gemini API (UPDATED for Scoring and Cleaned Whitespace)
def analyze_resume_gemini(resume_data, role=None, experience=None):
    text_content = "\n".join([
        span["text"] for page in resume_data["pages"] for span in page["text"]
    ])

    # Added instruction to calculate a score and included it in the expected JSON format
    prompt = f"""
You are an expert career coach and interviewer.
Candidate applying for role: {role or 'General'}.
Experience level: {experience or 'Not specified'}.
Here is the resume content:

{text_content}

Please provide a detailed analysis:
1. Summary of candidate profile
2. Key strengths
3. Weaknesses / negatives
4. Missing skills/technologies
5. Suggestions to improve resume formatting
6. Areas where interviewers will likely focus
7. Skill gaps the candidate should work on
8. Any ATS (Applicant Tracking System) issues
9. Recommendations for template, layout, and readability
10. **Calculate an Overall Resume Score from 0 to 100** ats based score base give and +ve bases based on the criteria for the specified role and experience level, focusing on relevance, completeness, and quality here consider all things and it elgigble a better stable overall score giv it may same if same resume comes in n  number of times means here consider all +ve and -ve can give score not always focus on -ve ,balance the -ve and +ve and a bettera cucurate ats like resume score give.

Format as JSON with keys:
**score** (integer from 0-100), summary, strengths, weaknesses, missing_skills, formatting_suggestions,
interview_focus, skill_gaps, ATS_issues, template_suggestions
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"

    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        content_text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        try:
            # Cleaned logic and fixed indentation
            cleaned_text = (
                content_text.strip()
                .replace("```json", "")
                .replace("```", "")
            )
            analysis_data = json.loads(cleaned_text)
            
            # Ensure the score is cast to an integer
            if 'score' in analysis_data and analysis_data['score'] is not None:
                analysis_data['score'] = int(analysis_data['score'])
                
            return analysis_data
        except json.JSONDecodeError:
            # Fixed indentation for proper exception handling
            return {"analysis_text": content_text}
    else:
        return {"error": response.text, "status_code": response.status_code}


# Main API (UPDATED for Scoring)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resume_analysis(request):
    role = request.data.get("role")
    experience = request.data.get("experience")
    resume_file = request.FILES.get("resume")
    user = request.user
    if not resume_file:
        return Response({"error": "Please upload a resume file."}, status=400)

    if not (
        resume_file.name.endswith(".pdf")
        or resume_file.name.endswith(".docx")
        or resume_file.name.endswith(".doc")
    ):
        return Response(
            {"error": "Unsupported file type. Please upload a PDF, DOC, or DOCX file."},
            status=400,
        )

    # Save temporarily
    temp_path = default_storage.save(f"temp/{resume_file.name}", resume_file)
    abs_path = os.path.join(settings.MEDIA_ROOT, temp_path)

    try:
        # Extract text
        if not resume_file.name.endswith(".pdf"):
            resume_data = {
                "pages": [
                    {
                        "text": [
                            {"text": "File content could not be extracted directly (non-PDF)."},
                            {"text": f"Filename: {resume_file.name}"},
                        ]
                    }
                ]
            }
        else:
            resume_data = extract_resume_details(abs_path)

        # Analyze via Gemini
        analysis = analyze_resume_gemini(resume_data, role, experience)

        score = analysis.get("score", 0)
        if score >= 66:
            performance = "good"
        elif score >= 46:
            performance = "average"
        else:
            performance = "poor"

        # --- Update or create Resume record ---
        resume_obj, _ = Resume.objects.get_or_create(user=user)
        resume_obj.performance = performance
        resume_obj.resume_count = resume_obj.resume_count + 1
        resume_obj.last_parsed_date = timezone.now()
        resume_obj.save()

    finally:
        # Clean up temporary file
        if os.path.exists(abs_path):
            os.remove(abs_path)

    final_response = {
        "status": "success",
        "job_details": {
            "role": role,
            "experience_level": experience,
        },
        "extracted_resume_data": {
            "text_and_format_details": resume_data["pages"]
        },
        "gemini_analysis": {
            # Added the dynamic score from the analysis
            "score": analysis.get("score"), 
            "summary": analysis.get("summary"),
            "strengths": analysis.get("strengths"),
            "weaknesses": analysis.get("weaknesses"),
            "missing_skills": analysis.get("missing_skills"),
            "formatting_suggestions": analysis.get("formatting_suggestions"),
            "interview_focus_areas": analysis.get("interview_focus"),
            "skill_gaps": analysis.get("skill_gaps"),
            "ats_issues": analysis.get("ATS_issues"),
            "template_recommendations": analysis.get("template_suggestions"),
            "analysis_error": analysis.get("error"),
            "raw_analysis_text_fallback": analysis.get("analysis_text"),
        },
    }

    if final_response["gemini_analysis"]["analysis_error"]:
        status_code = final_response["gemini_analysis"].get("status_code", 500)
        final_response["status"] = "analysis_failed"
        return Response(final_response, status=status_code)

    return Response(final_response, status=200)



    # learning_app/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction 
from django.utils.dateformat import format
from .models import CourseProgress

# --- Updated Default Courses ---
DEFAULT_COURSES = [
    {"course_name": "Full Stack Developer Path", "total_modules": 12},
    {"course_name": "System Design Mastery", "total_modules": 12},
    {"course_name": "Algorithm Interview Prep", "total_modules": 15},
    {"course_name": "Docker and Kubernetes Deep Dive", "total_modules": 8},
]

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_or_create_courses(request):
    """
    API endpoint for the dashboard to fetch all course summaries.
    Creates default progress records if the user has none.
    """
    user = request.user
    user_courses = CourseProgress.objects.filter(user=user)
    
    if not user_courses.exists():
        with transaction.atomic():
            progress_objects = []
            for course in DEFAULT_COURSES:
                progress_objects.append(
                    CourseProgress(
                        user=user,
                        course_name=course["course_name"],
                        total_modules=course["total_modules"],
                        completed_modules=[],
                        progress_percent=0.0,
                        is_completed=False,
                        started=False,
                        ended=False,
                        last_updated=timezone.now()
                    )
                )
            
            CourseProgress.objects.bulk_create(progress_objects)
            user_courses = CourseProgress.objects.filter(user=user)
    
    # Prepare data to return (Manual JSON Construction)
    course_data = []
    i=1
    for course in user_courses:
        course_data.append({
            "id": i, 
            "course_name": course.course_name,
            "total_modules": course.total_modules,
            # Note: completed_modules contains the list of IDs, its length gives the count
            "completed_modules": course.completed_modules, 
            "progress_percent": course.progress_percent,
            "is_completed": course.is_completed,
            "started": course.started,
            "ended": course.ended,
            "last_updated": format(course.last_updated, 'Y-m-d\TH:i:sP'),
        })
        i=i+1

    return Response({
        "status": "success",
        "data": course_data
    }, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_course(request):
    """
    Sets the 'started' flag to True for a given course.
    """
    user = request.user
    course_name = request.data.get('course_name')

    if not course_name:
        return Response({"status": "error", "message": "Missing 'course_name' in request data."}, 
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        course_progress = CourseProgress.objects.get(user=user, course_name=course_name)
    except CourseProgress.DoesNotExist:
        return Response({"status": "error", "message": f"Course '{course_name}' not found for user."}, 
                        status=status.HTTP_404_NOT_FOUND)

    if not course_progress.started:
        course_progress.started = True
        course_progress.last_updated = timezone.now()
        course_progress.save(update_fields=['started', 'last_updated'])
        return Response({"status": "success", "message": f"Course '{course_name}' marked as started.", "started": True}, 
                        status=status.HTTP_200_OK)
    
    return Response({"status": "success", "message": f"Course '{course_name}' was already started.", "started": True}, 
                    status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_module(request):
    """
    Adds a module ID to the completed_modules list and updates progress.
    """
    user = request.user
    course_name = request.data.get('course_name')
    module_id = request.data.get('module_id')

    if not course_name or module_id is None:
        return Response({"status": "error", "message": "Missing 'course_name' or 'module_id' in request data."}, 
                        status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # module_id is often an integer, ensure it's treated as such if necessary for storage
        module_id = int(module_id) 
    except ValueError:
        return Response({"status": "error", "message": "Invalid 'module_id' format. Must be an integer."}, 
                        status=status.HTTP_400_BAD_REQUEST)


    try:
        course_progress = CourseProgress.objects.get(user=user, course_name=course_name)
    except CourseProgress.DoesNotExist:
        return Response({"status": "error", "message": f"Course '{course_name}' not found for user."}, 
                        status=status.HTTP_404_NOT_FOUND)

    # 1. Update completed_modules list
    completed_modules_list = course_progress.completed_modules if course_progress.completed_modules is not None else []
    
    if module_id not in completed_modules_list:
        completed_modules_list.append(module_id)
        
        # 2. Recalculate progress
        total = course_progress.total_modules
        completed_count = len(completed_modules_list)
        
        # Calculate new progress percentage (rounded to 1 decimal place)
        new_progress_percent = round((completed_count / total) * 100, 1) if total > 0 else 0.0
        
        # 3. Check for completion
        is_completed = completed_count >= total
        
        # 4. Update the record
        course_progress.completed_modules = completed_modules_list
        course_progress.progress_percent = new_progress_percent
        course_progress.is_completed = is_completed
        course_progress.last_updated = timezone.now()
        
        # If the course is completed, you might want to set ended=True as well
        if is_completed and not course_progress.ended:
            course_progress.ended = True
            
        course_progress.save(update_fields=[
            'completed_modules', 
            'progress_percent', 
            'is_completed', 
            'ended',
            'last_updated'
        ])

        # --- GAMIFICATION UPDATE ---
        try:
            profile = user.profile
            xp_gain = 10
            profile.xp += xp_gain
            
            # Level Up Logic (Simple: Level * 100 XP required for next level)
            required_xp = profile.level * 100
            leveled_up = False
            
            while profile.xp >= required_xp:
                profile.xp -= required_xp
                profile.level += 1
                leveled_up = True
                required_xp = profile.level * 100 # Next level needs more XP
            
            profile.save()
        except Exception as e:
            print(f"Gamification Error: {e}")
            # Non-blocking error
            leveled_up = False
        
        return Response({
            "status": "success", 
            "message": f"Module {module_id} completed for '{course_name}'.",
            "progress_percent": new_progress_percent,
            "completed_modules_count": completed_count,
            "is_completed": is_completed,
            "xp_gained": 10,
            "leveled_up": leveled_up,
            "current_level": profile.level,
            "current_xp": profile.xp
        }, status=status.HTTP_200_OK)

    return Response({
        "status": "success", 
        "message": f"Module {module_id} was already completed for '{course_name}'. No change made."
    }, status=status.HTTP_200_OK)



# --- NEW HELPER FUNCTION FOR KNOWLEDGE POINT MANAGEMENT ---



def get_or_create_daily_knowledge_point():
    """
    Ensures a single KnowledgePoint (title, content) is created for today.
    - If already exists and is valid, it is returned.
    - If it exists but is a fallback, it attempts to regenerate and update the content.
    - Else (if no point exists), it is generated via Gemini, saved, and returned.
    """
    today = timezone.now().date()

    # 1. Check if today's KnowledgePoint already exists
    kp_today = KnowledgePoint.objects.filter(last_updated=today).first()
    
    # Check if the existing point is a fallback based on the title prefix
    is_fallback = kp_today and kp_today.title.startswith("Fallback KnowledgePoint")

    if kp_today and not is_fallback:
        # Case A: Valid point exists (not a fallback), return it immediately.
        return kp_today.title, kp_today.content

    # --- Generate content via Gemini (Attempt generation if no point exists or if it's a fallback) ---
    prompt = """
You are an expert career coach and tech mentor.
Create a unique, innovative knowledge point related to current IT industry trends,
skill improvement, and job-oriented learning.
Provide a catchy title and detailed description.
here not inclde ** like and give one small paragraph and consize all content with small and all information.
Return ONLY the raw JSON object with keys: title, content. Do NOT include markdown formatting.
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # Set initial values for the result (defaults to a new fallback if no kp_today exists)
    title_result = f"Fallback KnowledgePoint {today}"
    content_result = "Content generation failed. Trying again later."

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Extract and parse JSON from Gemini response
        raw_text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "{}")
        )
        
        gemini_json = json.loads(raw_text)
        print(gemini_json)
        # If successful, use Gemini's content
        title_result = gemini_json.get("title", title_result)
        content_result = gemini_json.get("content", content_result)

    except Exception:
        # Case C: Generation failed.
        # If kp_today was a fallback, we return the old fallback content.
        if is_fallback:
            print("erroor")
          
            return kp_today.title, kp_today.content
        # Otherwise (no point existed), we return the default new fallback.
        pass 

    # 3. Save or Update to DB
    if kp_today:
        # Update the existing record (either successful generation or overwriting old fallback with new fallback)
        kp_today.title = title_result
        kp_today.content = content_result
        kp_today.save()
        return kp_today.title, kp_today.content
    else:
        # Create a new record (either successful generation or a new fallback)
        kp_new = KnowledgePoint.objects.create(
            title=title_result,
            content=content_result
        )
        return kp_new.title, kp_new.content


# --- EXISTING HELPER FUNCTIONS ---

def time_ago(dt):
    """Converts a datetime object to a human-readable 'time ago' string."""
    now = timezone.now()
    if not dt:
        return 'N/A'

    diff = now - dt

    if diff < timedelta(minutes=1):
        return "just now"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() // 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() // 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff < timedelta(days=30):
        days = diff.days
        return f"{days} day{'s' if days > 1 else ''} ago"
    elif diff < timedelta(days=365):
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"




# --- MODIFIED HELPER FUNCTION ---

# The necessary imports (Count, TruncMonth, timezone) are assumed to be present.

def get_performance_chart_data(user, daily_count_instance):
    """
    Generates the 12-month activity performance data array for the current year,
    including the total active days and the monthly count of completed interviews.
    
    The 'score' key is replaced by 'activeDays'.
    """
    MONTHS_MAP = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
    }
    
    today = timezone.now()
    current_year = today.year
    chart_data = []

    # 1. Fetch completed Interview counts for the current year
    interview_counts = InterviewSession.objects.filter(
        user=user,
        completed=True,
        created_at__year=current_year
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        count=Count('id')
    )
    
    # Convert query results into a lookup dictionary: {'YYYY-MM': count}
    interview_count_map = {}
    for item in interview_counts:
        month_key = item['month'].strftime("%Y-%m")
        interview_count_map[month_key] = item['count']

    # 2. Iterate through months and build the final data structure
    for month_num, month_abbr in MONTHS_MAP.items():
        month_key = f"{current_year}-{month_num:02d}"
        
        # --- Active Days Count (from DailyCount) ---
        # The value is the raw count of active days for the month.
        days_active_count = daily_count_instance.month_wise_count.get(month_key, 0)
        
        # --- Interview Count (from InterviewSession) ---
        monthly_interviews = interview_count_map.get(month_key, 0)
        
        # For future months in the current year, set the count to 0
        if month_num > today.month:
            days_active_count = 0
            monthly_interviews = 0
            
        chart_data.append({
            "month": month_abbr,
            "activeDays": days_active_count,    # NEW KEY: Raw count of active days
            "interviews": monthly_interviews    # Completed Interview Count
        })
        
    return chart_data
# ------------------------------------------------------------------------
# --- POINTS CALCULATION FUNCTION (MODIFIED) ---
# ------------------------------------------------------------------------

def calculate_user_points(user):
    """
    Calculates total user points based on completed interviews and learning modules.

    Points System:
    - Easy Interview: 15 points
    - Medium Interview: 25 points
    - Hard Interview: 50 points
    - Each completed learning module in the completed_modules list: 10 points (CORRECTED)
    """
    total_points = 0

    # 1. Interview Points
    completed_interviews = InterviewSession.objects.filter(user=user, completed=True)
    
    for interview in completed_interviews:
        # Check the difficulty field (assuming it exists and stores 'easy', 'medium', or 'hard')
        difficulty = getattr(interview, 'difficulty', 'easy').lower()
        
        if difficulty == 'hard':
            total_points += 50
        elif difficulty == 'medium':
            total_points += 25
        else: # Default to easy if field is missing or unknown
            total_points += 15

    # 2. Learning Module Points (REFINED LOGIC)
    
    # Fetch all CourseProgress instances for the user
    all_course_progresses = CourseProgress.objects.filter(user=user)
    
    total_completed_modules_count = 0
    
    for progress in all_course_progresses:
        # Count the number of items (module IDs) in the completed_modules list
        # We ensure it's a list before getting the length to avoid errors.
        if isinstance(progress.completed_modules, list):
            total_completed_modules_count += len(progress.completed_modules)
            
    # Each completed module is 10 points
    total_points += total_completed_modules_count * 10 

    return total_points
# --- MAIN VIEW FUNCTION (UPDATED) ---

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_data_view(request):
    user = request.user
    
    # 1. SIDE EFFECT: Update DailyCount Streak
    daily_count_instance, _ = DailyCount.objects.get_or_create(user=user)
    daily_count_instance.update_streak_and_month()
    
    # 2. SIDE EFFECT: Ensure today's Knowledge Point is generated
    get_or_create_daily_knowledge_point() 
    
    # --- A. Quick Stats ---
    user_total_points = calculate_user_points(user)

    last_interview = InterviewSession.objects.filter(user=user, completed=True).order_by('-created_at').first()
    last_interview_data = {
        'title': last_interview.course if last_interview else 'N/A',
        'date': time_ago(last_interview.created_at) if last_interview else 'Not yet started!',
    }

    try:
        # Field: Resume.performance
        resume_instance = Resume.objects.get(user=user)
        resume_performance_data = resume_instance.performance
    except Resume.DoesNotExist:
        resume_performance_data = None

    last_course_progress = CourseProgress.objects.filter(user=user).order_by('-last_updated').first()
    last_course_data = {
        # Field: CourseProgress.course_name, CourseProgress.progress_percent, CourseProgress.last_updated
        'title': last_course_progress.course_name if last_course_progress else 'N/A',
        'progress': round(last_course_progress.progress_percent) if last_course_progress else 0,
        'date': time_ago(last_course_progress.last_updated) if last_course_progress else 'Not yet started!',
    }
    
    # Field: DailyCount.learning_days_streak
    learning_streak = daily_count_instance.learning_days_streak


    # --- B. Activity Performance Data (Chart) ---
    activity_performance_data = get_performance_chart_data(user, daily_count_instance)


    # --- C. Knowledge Points (FETCH) ---
    # Fetch 2 most recent KnowledgePoints globally
    knowledge_points = KnowledgePoint.objects.order_by('-last_updated')[:1]
    
    knowledge_points_data = [
        {
            'title': p.title, # Field: KnowledgePoint.title
            'content': p.content, # Field: KnowledgePoint.content
            # 'icon' field is omitted as requested.
        }
        for p in knowledge_points
    ]
    

    # --- D. Recent Activities (Timeline) ---
    
    recent_activities_list = []
    
    # 1. Interviews (Completed)
    interviews = InterviewSession.objects.filter(user=user, completed=True).order_by('-created_at')[:3]
    for interview in interviews:
        recent_activities_list.append({
            'timestamp': interview.created_at,
            'type': 'interview',
            'title': interview.course,
            'detail': 'Completed',
            'date': time_ago(interview.created_at),
            'icon': 'MessageSquare',
            'color': 'text-accent-blue',
            'progress': 0, 
        })

    # 2. Course Progress (Last Updated)
    courses = CourseProgress.objects.filter(user=user).exclude(progress_percent__gte=100.0).order_by('-last_updated')[:3]
    for course in courses:
        recent_activities_list.append({
            'timestamp': course.last_updated,
            'type': 'course',
            'title': course.course_name,
            'detail': f'Progress: {round(course.progress_percent)}%',
            'date': time_ago(course.last_updated),
            'icon': 'GraduationCap',
            'color': 'text-purple-500',
            'progress': round(course.progress_percent),
        })

    # 3. Resume Analysis (Last Parsed Date)
    if 'resume_instance' in locals() and resume_performance_data and resume_instance.last_parsed_date:
        recent_activities_list.append({
            'timestamp': resume_instance.last_parsed_date, # Field: Resume.last_parsed_date
            'type': 'resume',
            'title': 'Resume Analysis Completed',
            'detail': f'Performance: {resume_performance_data.capitalize()}',
            'date': time_ago(resume_instance.last_parsed_date),
            'icon': 'FileText',
            'color': 'text-accent-green',
            'progress': 0,
        })

    # Sort all activities by timestamp and take the top 3
    recent_activities_list.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_activities_final = recent_activities_list[:3]

    # Clean up the final list
    for activity in recent_activities_final:
        activity.pop('timestamp')


    # --- E. Final JSON Response Structure ---
    response_data = {
        'user': {
            'name': user.get_full_name() or user.username,
        },
        'quickStats': {
            'lastInterview': last_interview_data,
            'lastLearningCourse': last_course_data,
            'resumePerformance': resume_performance_data,
            'learningDaysStreak': learning_streak,
            'totalPoints': user_total_points,
        },
        'activityPerformanceData': activity_performance_data,
        'knowledgePoints': knowledge_points_data,
        'recentActivities': recent_activities_final,
    }

    return Response(response_data)



# --- HELPER FUNCTIONS ---

def get_points_for_difficulty(difficulty):
    """Maps interview difficulty to points."""
    return {'easy': 15, 'medium': 25, 'hard': 50}.get(difficulty.lower(), 15)




# ------------------------------------------------------------------------
# --- NEW VIEW FUNCTION FOR PROFILE STATS ---
# ------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile_stats_view(request):
    """
    Calculates and returns dynamic statistics and the last 5 point-achieving activities 
    for the user's profile page.
    """
    user = request.user
    
    # --- 1. QUICK STATS CALCULATION ---
    
    # 1.1 Interviews Completed
    total_interviews = InterviewSession.objects.filter(user=user, completed=True).count()
    
    # 1.2 Learning Streak
    try:
        daily_count_instance = DailyCount.objects.get(user=user)
        learning_days_streak = daily_count_instance.learning_days_streak
    except DailyCount.DoesNotExist:
        learning_days_streak = 0
        
    # 1.3 Skills Improved (Courses Completed)
    skills_improved = CourseProgress.objects.filter(
        user=user, 
        is_completed=True # Assuming a completed course means a skill is improved
    ).count()

    quick_stats = {
        "interviewsCompleted": total_interviews,
        "learningStreak": learning_days_streak,
        "skillsImproved": skills_improved,
    }


    # --- 2. RECENT POINTS ACHIEVED (Last 5 Activities) ---
    recent_activities = []
    
    # 2.1 Interviews
    interviews = InterviewSession.objects.filter(user=user, completed=True).order_by('-created_at')[:5]
    for interview in interviews:
        points = get_points_for_difficulty(interview.difficulty)
        recent_activities.append({
            'timestamp': interview.created_at,
            'type': 'interview',
            'title': f"{interview.course} Interview",
            'detail': f"Difficulty: {interview.difficulty.capitalize()}",
            'points': points,
            'date': time_ago(interview.created_at),
            'icon': 'MessageSquare',
            'color': 'text-accent-blue',
        })

    # 2.2 Course Module Completions
    # Fetch all courses the user has started/updated
    course_progresses = CourseProgress.objects.filter(user=user).exclude(completed_modules=[])
    
    # For simplicity, we track the *latest* progress update for a course, 
    # and show the points earned from all modules in that course *at that point*.
    for progress in course_progresses:
        completed_count = len(progress.completed_modules)
        if completed_count > 0:
            points = completed_count * 10
            
            # Use 'is_completed' status for title if fully done, otherwise use module count
            detail = f"{completed_count} module{'s' if completed_count > 1 else ''} completed"
            if progress.is_completed:
                 detail = "Course completed (100% progress)"

            recent_activities.append({
                'timestamp': progress.last_updated,
                'type': 'course',
                'title': progress.course_name,
                'detail': detail,
                'points': points,
                'date': time_ago(progress.last_updated),
                'icon': 'GraduationCap',
                'color': 'text-purple-500',
            })
            
    # 2.3 Combine, Sort, and Slice to Top 5
    recent_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    recent_points_achieved = recent_activities[:3]

    # Clean up the final list
    for activity in recent_points_achieved:
        activity.pop('timestamp')

    return Response({
        "quickStats": quick_stats,
        "recentPointsAchieved": recent_points_achieved
    })

# NOTE: You must add the following entry to your project's urls.py:
# path('profile-stats/', get_profile_stats_view, name='profile_stats'),


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def login_check(request):
    """
    Checks the user's login status.
    
    If the user is authenticated (token/session is valid), this view executes
    and returns a 200 OK status.
    
    If the user is NOT authenticated, the IsAuthenticated permission will
    intercept the request and automatically return a 401 Unauthorized response.
    """
    
    # If the code reaches this point, the user is successfully authenticated.
    # You can return minimal user data here if needed.
    return Response(
        {
            "message": "User is authenticated.",
            "is_logged_in": True,
            # Optional: Add basic user info if needed
            # "username": request.user.username,
        },
        status=status.HTTP_200_OK
    )
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gamification_profile(request):
    """
    Returns the user's gamification status (Level, XP, Inventory).
    """
    try:
        profile = request.user.profile
        return Response({
            "level": profile.level,
            "xp": profile.xp,
            "next_level_xp": profile.level * 100,
            "inventory": profile.inventory,
            "avatar": profile.profile_image
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def visualize_content(request):
    """
    Generates a Mermaid.js diagram definition from the provided text content using Gemini.
    """
    try:
        content = request.data.get('content')
        if not content:
            return Response({'error': 'Content is required'}, status=400)

        # Construct the prompt for Gemini
        prompt = f"""
        You are an expert technical educator. Your goal is to visualize the following technical concept using a Mermaid.js diagram.
        
        Analyze the text below and create a valid Mermaid.js chart (e.g., flowchart, sequence diagram, class diagram, or mindmap) that best represents the structure and relationships in the content.
        
        Rules:
        1. Return ONLY the raw Mermaid code. Do not include markdown code blocks (```mermaid ... ```).
        2. Do not include any explanation or other text.
        3. Use simple, clear node labels.
        4. If the content describes a process, use a flowchart (graph TD).
        5. If it describes a structure, use a class diagram or mindmap.
        
        Content to visualize:
        "{content[:2000]}"
        """

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
             return Response({
                "error": "Gemini API failed",
                "details": response.text
            }, status=502)

        data = response.json()
        try:
             mermaid_code = data['candidates'][0]['content']['parts'][0]['text'].strip()
        except (KeyError, IndexError):
             return Response({
                "error": "Invalid response format from Gemini",
                "raw_response": data
            }, status=502)

        # Cleanup if the model still wraps it in markdown (defensive coding)
        mermaid_code = re.sub(r"^```[a-zA-Z]*\n", "", mermaid_code)
        mermaid_code = re.sub(r"^```", "", mermaid_code)
        mermaid_code = re.sub(r"```$", "", mermaid_code)
        mermaid_code = mermaid_code.strip()

        return Response({'type': 'mermaid', 'chart': mermaid_code})

    except Exception as e:
        print(f"Visualization Error: {e}")
        return Response({'type': 'mermaid', 'chart': mermaid_code})

    except Exception as e:
        print(f"Visualization Error: {e}")
        return Response({'error': str(e)}, status=500)


# --- P2P Interview Views ---

from .models import InterviewMatch, InterviewQueue
from django.db.models import Q
import json

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def find_partner(request):
    user = request.user
    
    # 1. Cleanup old queue entries for this user
    InterviewQueue.objects.filter(user=user).delete()

    # 2. Check if already in active match? (Optional, maybe we want to force new)
    # active_match = InterviewMatch.objects.filter((Q(user1=user) | Q(user2=user)), status='active').first()
    # if active_match: ...

    # 3. Find opponent
    opponent_entry = InterviewQueue.objects.exclude(user=user).order_by('joined_at').first()
    
    if opponent_entry:
        opponent = opponent_entry.user
        opponent_entry.delete() # Remove from queue
        
        # Create Match
        match = InterviewMatch.objects.create(
            user1=user,
            user2=opponent,
            status='active',
            current_interviewer=user # User1 starts as interviewer
        )
        return Response({
            "status": "matched",
            "match_id": match.id,
            "partner": opponent.username,
            "role": "interviewer"
        })
    else:
        # Add to queue
        InterviewQueue.objects.create(user=user)
        return Response({"status": "waiting"})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def poll_match_status(request):
    user = request.user
    
    # Check if matched
    match = InterviewMatch.objects.filter(
        (Q(user1=user) | Q(user2=user)),
        status='active'
    ).order_by('-created_at').first()
    
    if match:
        partner = match.user2 if match.user1 == user else match.user1
        is_interviewer = match.current_interviewer == user
        
        # Signaling Logic
        my_role_key = "user1" if match.user1 == user else "user2"
        partner_role_key = "user2" if match.user1 == user else "user1"
        
        # Get partner's signal
        signals = match.signals or {}
        incoming_signal = signals.get(f"{partner_role_key}_signal")
        last_feedback = signals.get("last_feedbac") # Typo fix: feedback
        last_feedback = signals.get("last_feedback")

        return Response({
            "status": "matched",
            "match_id": match.id,
            "partner": partner.username,
            "role": "interviewer" if is_interviewer else "candidate",
            "incoming_signal": incoming_signal,
            "last_feedback": last_feedback
        })
    
    # Check if still in queue
    in_queue = InterviewQueue.objects.filter(user=user).exists()
    return Response({"status": "waiting" if in_queue else "idle"})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def exchange_signal(request):
    user = request.user
    match_id = request.data.get('match_id')
    signal_data = request.data.get('signal')
    
    try:
        match = InterviewMatch.objects.get(id=match_id)
        if user != match.user1 and user != match.user2:
             return Response({"error": "Not part of this match"}, status=403)
             
        my_role_key = "user1" if match.user1 == user else "user2"
        
        if not match.signals: match.signals = {}
        match.signals[f"{my_role_key}_signal"] = signal_data
        match.save()
        
        return Response({"status": "signal_sent"})
    except InterviewMatch.DoesNotExist:
        return Response({"error": "Match not found"}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def p2p_ai_feedback(request):
    """
    Analyzes the answer from the Candidate and provides feedback to BOTH users.
    """
    user = request.user
    match_id = request.data.get('match_id')
    text = request.data.get('answer_text', '')
    question = request.data.get('question', '')
    
    # TODO: Handle Audio Blob if implementing Speech-to-Text here or assuming text is passed
    # For now, let's assume valid text is passed (or we fallback to simple placeholder)
    
    try:
        match = InterviewMatch.objects.get(id=match_id)
        
        # Generate Gemini Feedback
        prompt = f"""
        You are supervising a peer-to-peer interview.
        Question asked: "{question}"
        Candidate Answer: "{text}"
        
        Provide brief, constructive feedback in JSON format:
        {{
            "feedback": "...",
            "rating": 1-5,
            "tip": "..."
        }}
        """
        
        # Call Gemini (Simulated or Real)
        # Reusing existing Gemini logic logic or copy-paste simplified
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
             gemini_res = response.json()
             try:
                 feedback_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
                 # Extract JSON
                 json_match = re.search(r'\{.*\}', feedback_text, re.DOTALL)
                 if json_match:
                     feedback_data = json.loads(json_match.group(0))
                 else:
                     feedback_data = {"feedback": feedback_text, "rating": 3, "tip": "Keep practicing."}
             except:
                 feedback_data = {"feedback": "Could not parse AI response.", "rating": 0, "tip": ""}
        else:
             feedback_data = {"feedback": "AI unavailable.", "rating": 0, "tip": ""}

        # Store feedback in Signal for Polling
        if not match.signals: match.signals = {}
        match.signals['last_feedback'] = feedback_data
        
        # Switch Turns?
        # status = "completed" if ... else "active"
        # Swap interviewer
        match.current_interviewer = match.user2 if match.current_interviewer == match.user1 else match.user1
        match.save()
        
        return Response(feedback_data)

    except InterviewMatch.DoesNotExist:
        return Response({"error": "Match not found"}, status=404)


