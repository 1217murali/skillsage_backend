from rest_framework import serializers
from .models import AppUser  # <- Use your custom model

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = AppUser
        fields = ('username', 'email', 'password')

    def create(self, validated_data):
        user = AppUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user


# profiles/serializers.py
from rest_framework import serializers
from django.conf import settings
from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["name", "email", "phone", "location", "title", "experience"]

    def get_name(self, obj):
        if obj.user:  # Prevent crash if no user linked
            return f"{obj.user.first_name} {obj.user.last_name}".strip()
        return ""

    def update(self, instance, validated_data):
        user = getattr(instance, "user", None)

        # Update user first/last name if user exists
        name = self.context["request"].data.get("name", "").strip()
        if user and name:
            parts = name.split(" ", 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ""
            user.save()

        # Update profile fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        return instance
