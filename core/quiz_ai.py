import json
import hashlib
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI
from .models import QuizAttempt, QuizQuestionBank

# Initialize OpenRouter Client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY
)

# You can toggle this to use GPT-4o-mini via OpenRouter
# e.g. "openai/gpt-4o-mini"
AI_MODEL = "google/gemini-2.5-flash" 

def extract_json(text):
    try:
        # If wrapped in markdown blocks
        if "```json" in text:
            content = text.split("```json")[1].split("```")[0].strip()
            return json.loads(content)
        elif "```" in text:
             content = text.split("```")[1].split("```")[0].strip()
             return json.loads(content)
        # Direct fallback
        return json.loads(text.strip())
    except Exception:
        return None

def generate_quiz_question(module_id, difficulty):
    """
    Calls out to the LLM to generate a single quiz question.
    """
    prompt = f"""
    You are an expert technical instructor. Generate a SINGLE educational multiple-choice quiz question.
    
    Topic Context (Module ID): {module_id}
    Difficulty Target: {difficulty} (where 'easy' is for beginners, 'medium' is intermediate, and 'hard' is advanced)
    
    Requirements:
    - Must have exactly 4 options.
    - Must be educational and factually accurate.
    
    Output strictly as JSON in the following format, with no markdown formatting or extra text:
    {{
        "question": "The question text here...",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option A",
        "explanation": "A short explanation of why this is the correct answer.",
        "difficulty": "{difficulty}",
        "topic": "The specific micro-topic this covers (e.g. Flexbox, React Hooks, etc)"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        content = response.choices[0].message.content
        return extract_json(content)
    except Exception as e:
        print(f"Error generating question: {e}")
        return None

def hash_question(text):
    """Creates MD5 hash of the question text for quick duplicate checking."""
    return hashlib.md5(text.lower().strip().encode('utf-8')).hexdigest()

def is_duplicate(user, module_id, question_hash):
    """Checks if the user has already seen this question hash in this module."""
    return QuizAttempt.objects.filter(
        user=user, 
        module_id=module_id, 
        question_hash=question_hash
    ).exists()

def fallback_to_bank(module_id, difficulty, exclude_hashes=None):
    """Fallback method if AI generation fails or duplicates too much."""
    if exclude_hashes is None:
        exclude_hashes = []
        
    # Map 'easy' 'medium' 'hard' to 1-5 scale roughly
    diff_map = {'easy': [1, 2], 'medium': [3], 'hard': [4, 5]}
    target_diffs = diff_map.get(difficulty.lower(), [3])
    
    # Try finding an unused question from the DB bank
    # Note: question bank does not store hashes by default, so we check on the fly
    bank_questions = QuizQuestionBank.objects.filter(
        module_id=module_id,
        base_difficulty__in=target_diffs
    ).order_by('?')[:20] # grab a random sample to check
    
    for q in bank_questions:
        q_hash = hash_question(q.question_text)
        if q_hash not in exclude_hashes:
            return {
                "id": str(q.id),
                "question": q.question_text,
                "options": q.options,
                "correct_answer": q.options[q.correct_answer_index] if q.options else "",
                "correct_answer_index": q.correct_answer_index,
                "explanation": "From curated question bank.",
                "difficulty": difficulty,
                "topic": "General",
                "is_fallback": True
            }
    return None

def get_adaptive_question(user, module_id, difficulty):
    """
    Orchestrates generation, anti-duplication, and caching.
    Attempts to generate up to 3 times before falling back.
    """
    
    cache_key_prefix = f"quiz_gen_{user.id}_{module_id}_{difficulty}"
    
    # Check what hashes we should avoid
    past_attempts = set(QuizAttempt.objects.filter(user=user, module_id=module_id).values_list('question_hash', flat=True))
    
    max_retries = 3
    for _ in range(max_retries):
        ai_q = generate_quiz_question(module_id, difficulty)
        
        if ai_q and 'question' in ai_q:
            q_hash = hash_question(ai_q['question'])
            
            if q_hash not in past_attempts:
                # Add index to the correct answer for frontend compatibility
                try:
                    correct_idx = ai_q['options'].index(ai_q['correct_answer'])
                except ValueError:
                    correct_idx = 0 # Fallback if AI messes up the exact string match
                
                ai_q['correct_answer_index'] = correct_idx
                ai_q['hash'] = q_hash
                
                # We can cache it individually or just return it immediately
                # If we generated batches, we would cache the rest here.
                return ai_q
    
    # If all generation fails or duplicates, use fallback
    return fallback_to_bank(module_id, difficulty, exclude_hashes=past_attempts)
