from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpResponseRedirect
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
User = get_user_model()
class NoNewUserSignupAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True  # You can restrict here if needed

class NoSignupSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # If already associated, no need to do anything
        if sociallogin.is_existing:
            return

        # Check if a user already exists with this email
        email = sociallogin.account.extra_data.get("email")
        if email:
            try:
                user = User.objects.get(email=email)
                # Link the existing user to this social login
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass 
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        user.save()
        return user

