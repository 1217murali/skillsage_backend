import os
import joblib
import pandas as pd
import io
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from datetime import timedelta
from django.utils import timezone
from .models import QuizAttempt, UserModuleStat, UserModelStore

def calculate_streak(attempts):
    """Calculates the current streak of correct answers from a list of attempts."""
    streak = 0
    for a in reversed(attempts):
        if a.is_correct:
            streak += 1
        else:
            break
    return streak

def train_user_model(user, module_id):
    """
    Trains a Logistic Regression model for a specific user and module
    based on their QuizAttempt history. Stores in SQLite UserModelStore.
    """
    attempts = list(QuizAttempt.objects.filter(user=user, module_id=module_id).order_by('timestamp'))
    
    if len(attempts) < 10: # Minimum 10 attempts to train
        return False

    # Extract advanced V2 features
    data = []
    
    for i, attempt in enumerate(attempts):
        start_idx = max(0, i - 10)
        recent_window = attempts[start_idx:i]
        
        trailing_accuracy = 0.5
        if len(recent_window) > 0:
            trailing_accuracy = sum(1 for r in recent_window if r.is_correct) / len(recent_window)
        
        # Calculate time decay (hours since previous question)
        time_decay_hours = 0
        if i > 0:
            delta = attempt.timestamp - attempts[i-1].timestamp
            time_decay_hours = delta.total_seconds() / 3600.0

        session_streak = calculate_streak(attempts[:i])
        
        # Base difficulty encoding roughly 1-5
        diff_map = {'easy': 1, 'medium': 3, 'hard': 5}
        d_val = diff_map.get(attempt.difficulty.lower(), 3)
        
        conf = attempt.confidence_rating if attempt.confidence_rating else 3

        data.append({
            'difficulty_val': d_val,
            'time_taken': attempt.time_taken_seconds,
            'trailing_accuracy': trailing_accuracy,
            'confidence': conf,
            'session_streak': session_streak,
            'time_decay': time_decay_hours,
            'is_correct': 1 if attempt.is_correct else 0
        })
        
    df = pd.DataFrame(data)
    
    # Needs both correct and incorrect answers to train a binary classifier
    if len(df['is_correct'].unique()) < 2:
        return False

    X = df[['difficulty_val', 'time_taken', 'trailing_accuracy', 'confidence', 'session_streak', 'time_decay']]
    y = df['is_correct']

    # Train Model
    model = LogisticRegression(class_weight='balanced', max_iter=200)
    model.fit(X, y)

    # Serialize to memory buffer
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    binary_model_data = buffer.getvalue()

    # Save to SQLite Database
    store, _ = UserModelStore.objects.get_or_create(user=user, module_id=module_id)
    store.model_data = binary_model_data
    store.training_samples_count = len(attempts)
    store.save()

    return True

def predict_next_difficulty(user, module_id):
    """
    Uses the trained model to predict the probability of success 
    for an 'average' medium question right now. Maps that to target difficulty.
    """
    store = UserModelStore.objects.filter(user=user, module_id=module_id).first()
    
    # If no model trained yet, return 'medium' as default, or cold start logic handles it upstream
    if not store or not store.model_data:
        return 'medium'

    # Load model from DB BinaryField
    buffer = io.BytesIO(store.model_data)
    try:
        model = joblib.load(buffer)
    except Exception as e:
        print(f"Error loading model from DB: {e}")
        return 'medium'

    # Assemble current real-time feature state to predict against
    attempts = list(QuizAttempt.objects.filter(user=user, module_id=module_id).order_by('-timestamp')[:10])
    attempts.reverse() # chronologically
    
    if not attempts:
        return 'medium'

    trailing_accuracy = sum(1 for r in attempts if r.is_correct) / len(attempts)
    session_streak = calculate_streak(attempts)
    
    last_attempt = attempts[-1]
    time_decay_hours = (timezone.now() - last_attempt.timestamp).total_seconds() / 3600.0
    
    # Predict for a hypothetical 'medium' difficulty question with assumed average time
    hypothetical_features = pd.DataFrame([{
        'difficulty_val': 3, 
        'time_taken': 30, # Assumed 30s
        'trailing_accuracy': trailing_accuracy,
        'confidence': 3,  # Assumed neutral confidence
        'session_streak': session_streak,
        'time_decay': time_decay_hours,
    }])

    prob_success = model.predict_proba(hypothetical_features)[0][1] # Probability of class 1 (Correct)

    # Target Mapping
    if prob_success > 0.80:
        return 'hard'
    elif prob_success < 0.60:
        return 'easy'
    else:
        return 'medium'
