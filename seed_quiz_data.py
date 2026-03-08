import os
import sys
import django

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'skillsageai.settings')
django.setup()

from core.models import QuizQuestionBank

def seed_data():
    questions = [
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "What does CSS stand for?",
            "options": ["Cascading Style Sheets", "Creative Style System", "Computer Style Sheets", "Colorful Style Sheets"],
            "correct_answer_index": 0,
            "base_difficulty": 1
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "Which of the following is not a JavaScript data type?",
            "options": ["Undefined", "Number", "Boolean", "Float"],
            "correct_answer_index": 3,
            "base_difficulty": 2
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "What is the purpose of the z-index property in CSS?",
            "options": ["To spin elements", "To adjust element transparency", "To define the stack order of elements", "To create a zig-zag animation"],
            "correct_answer_index": 2,
            "base_difficulty": 3
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "Which HTTP method is typically used to update an existing resource?",
            "options": ["GET", "POST", "PUT", "DELETE"],
            "correct_answer_index": 2,
            "base_difficulty": 4
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "In React, what is the primary purpose of the useEffect hook?",
            "options": ["To style components", "To handle state mutations directly", "To perform side effects in function components", "To route between pages"],
            "correct_answer_index": 2,
            "base_difficulty": 5
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "What does HTML stand for?",
            "options": ["Hyper Text Markup Language", "High Text Machine Language", "Hyper Tabular Markup Language", "High Text Markup Language"],
            "correct_answer_index": 0,
            "base_difficulty": 1
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "Which tag is used to create a hyperlink in HTML?",
            "options": ["<link>", "<a>", "<href>", "<hyperlink>"],
            "correct_answer_index": 1,
            "base_difficulty": 1
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "How do you declare a variable in modern JavaScript?",
            "options": ["variable x;", "v x;", "let x;", "def x;"],
            "correct_answer_index": 2,
            "base_difficulty": 1
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "What is the purpose of 'box-sizing: border-box' in CSS?",
            "options": ["Adds a border to the box", "Includes padding and border in the element's total width and height", "Removes all borders", "Makes the box circular"],
            "correct_answer_index": 1,
            "base_difficulty": 3
        },
        {
            "course_name": "Web Development",
            "module_id": "m-101",
            "question_text": "Explain the concept of 'closure' in JavaScript.",
            "options": ["Closing a browser tab", "A function having access to its parent scope even after the parent function has closed", "Ending a loop", "A way to hide HTML elements"],
            "correct_answer_index": 1,
            "base_difficulty": 4
        }
    ]

    count = 0
    for q in questions:
        obj, created = QuizQuestionBank.objects.get_or_create(
            module_id=q["module_id"],
            question_text=q["question_text"],
            defaults={
                "course_name": q["course_name"],
                "options": q["options"],
                "correct_answer_index": q["correct_answer_index"],
                "base_difficulty": q["base_difficulty"]
            }
        )
        if created:
            count += 1

    print(f"Successfully seeded {count} new questions.")

if __name__ == "__main__":
    seed_data()
