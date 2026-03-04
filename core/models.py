from django.db import models

# Create your models here.
from django.db import models

# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db import models

class AppUser(AbstractUser):
    email = models.EmailField(unique=True)
    login_method = models.CharField(max_length=20, choices=[('email', 'Email'), ('google', 'Google')], default='email')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # Still needed for admin panel

# core/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

User = get_user_model()

class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(hours=1)

    def __str__(self):
        return f"{self.user.email} - {self.token}"
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=20, blank=True, default="")
    location = models.CharField(max_length=100, blank=True, default="Not specified")
    title = models.CharField(max_length=100, blank=True, default="Not specified")
    experience = models.CharField(max_length=50, blank=True, default="0 years")
    profile_image = models.URLField(blank=True,null=True,default="https://i.imgur.com/7suwDp5.jpeg")
    
    # Gamification Fields
    level = models.IntegerField(default=1)
    xp = models.IntegerField(default=0)
    inventory = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.user.email}'s Profile"

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        instance.profile.save()



# models.py
from django.db import models


class InterviewSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=50, choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')])
    total_duration = models.IntegerField(default=25)  # in minutes
    created_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.course} ({self.difficulty})"


class InterviewQuestion(models.Model):
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    allocated_time = models.IntegerField()  # seconds per question
    order = models.IntegerField()

    def __str__(self):
        return f"Q{self.order} - {self.question_text[:50]}"


class InterviewAnswer(models.Model):
    question = models.ForeignKey(InterviewQuestion, on_delete=models.CASCADE, related_name="answers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    answer_text = models.TextField()
    time_taken = models.IntegerField()  # seconds
    feedback = models.TextField(blank=True, null=True)
    rating = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Answer by {self.user.username} for {self.question.id}"



from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import JSONField # Use JSONField from django.db.models

class CourseProgress(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_progress"
    )
    course_name = models.CharField(max_length=255)

    total_modules = models.PositiveIntegerField(default=0)
    completed_modules = JSONField(default=list)  # e.g., ["M-101", "M-102"]

    progress_percent = models.FloatField(default=0.0)
    is_completed = models.BooleanField(default=False)

    started = models.BooleanField(default=False)
    ended = models.BooleanField(default=False)

    last_updated = models.DateTimeField(default=timezone.now)

    class Meta:
        # CORRECTION: Added unique_together constraint
        unique_together = ('user', 'course_name') 

    def save(self, *args, **kwargs):
        """Auto-update progress whenever record is saved."""
        if self.total_modules > 0:
            self.progress_percent = (len(self.completed_modules) / self.total_modules) * 100
            self.is_completed = len(self.completed_modules) >= self.total_modules
        else:
            self.progress_percent = 0.0
            self.is_completed = False
            
        self.last_updated = timezone.now()
        super().save(*args, **kwargs)

    def add_completed_module(self, module_id):
        """Add a new module and auto-update progress."""
        if module_id not in self.completed_modules:
            self.completed_modules.append(module_id)
            self.save()

    def remove_completed_module(self, module_id):
        """Remove a module and auto-update progress."""
        if module_id in self.completed_modules:
            self.completed_modules.remove(module_id)
            self.save()

    def __str__(self):
        return f"{self.user.username} - {self.course_name} ({self.progress_percent:.1f}%)"   



from django.db import models
from django.contrib.auth import get_user_model # To reference the default User model

# Get the custom or default User model
User = get_user_model()

# --- 1. Resume Model ---
# Stores resume analysis information specific to a user.

class Resume(models.Model):
    """
    Model to track a user's resume performance and last analysis date.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='resume_profile',
        verbose_name="User"
    )
    
    performance = models.CharField(
        max_length=10,
        choices=[
            ('poor', 'Poor'),
            ('average', 'Average'),
            ('good', 'Good')
        ],
        null=True,
        blank=True,
        verbose_name="Resume Performance"
    )
    resume_count = models.IntegerField(
        default=1,
        verbose_name="Current Learning Streak (Days)"
    )
    last_parsed_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last Analysis Date"
    )

    def __str__(self):
        return f"Resume Profile for {self.user.username}"

# --- 2. KnowledgePoint Model ---
# Stores global knowledge points/mastery concepts, NOT tied to a specific user.

class KnowledgePoint(models.Model):
    """
    Model for key knowledge or mastery areas (e.g., Deep Dive: Hooks Optimization).
    This is static content/metadata, not per-user data.
    """
    title = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Knowledge Point Title"
    )
    
    content = models.TextField(
        verbose_name="Detailed Description"
    )

    last_updated = models.DateField(
        auto_now=True,  # Automatically set the date every time the object is saved
        verbose_name="Last Content Update"
    )

    def __str__(self):
        return self.title

from django.db import models

from django.utils import timezone
from django.db.models import JSONField  # Django 3.1+


class DailyCount(models.Model):
    """
    Model to track a user's learning days streak and month-wise activity.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='daily_count',
        verbose_name="User"
    )

    learning_days_streak = models.IntegerField(
        default=0,
        verbose_name="Current Learning Streak (Days)"
    )

    count_last_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Last Streak Update Date"
    )

    # 🆕 Month-wise activity record: stores total active days per month
    month_wise_count = JSONField(default=dict, blank=True)
    # Example:
    # {
    #     "2025-10": 12,   # User active 12 days in October 2025
    #     "2025-09": 8,    # User active 8 days in September 2025
    # }

    def __str__(self):
        return f"{self.user.username}'s Streak: {self.learning_days_streak} days"

    def update_streak_and_month(self):
        """
        Update daily streak and month-wise count when user is active today.
        """
        today = timezone.now().date()
        month_key = today.strftime("%Y-%m")  # e.g., "2025-10"

        # Update streak
        if self.count_last_date == today:
            return  # Already counted today

        if self.count_last_date == today - timezone.timedelta(days=1):
            self.learning_days_streak += 1  # continue streak
        else:
            self.learning_days_streak = 1  # reset streak

        self.count_last_date = today

        # Update month-wise count
        self.month_wise_count[month_key] = self.month_wise_count.get(month_key, 0) + 1

        self.save()


# --- P2P Interview Models ---

class InterviewMatch(models.Model):
    """
    Represents a P2P interview session between two users.
    Uses Polling-based signaling for WebRTC.
    """
    user1 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_as_user1")
    user2 = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_as_user2", null=True, blank=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('active', 'Active'), ('completed', 'Completed')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Store WebRTC signals exchanged via polling
    # Structure: {"user1": {"offer": ..., "ice": []}, "user2": {"answer": ..., "ice": []}}
    signals = models.JSONField(default=dict, blank=True)
    
    # Track who is currently "Interviewer" (asking questions)
    current_interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="interviewing_matches")

    def __str__(self):
        u2 = self.user2.username if self.user2 else "Waiting"
        return f"{self.user1.username} vs {u2} ({self.status})"

class InterviewQueue(models.Model):
    """
    Queue for users waiting to find a partner.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} waiting since {self.joined_at}"

