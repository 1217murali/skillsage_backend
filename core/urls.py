from django.urls import path
from .views import GoogleLoginAPIView
from .views import RegisterView,ProfileView
from . import views
from django.contrib.auth import views as auth_views
from rest_framework_simplejwt.views import TokenRefreshView
urlpatterns = [
    path('google-login/', GoogleLoginAPIView.as_view()),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', views.CustomLoginView.as_view(), name='token_obtain_pair'),
    path('password-reset/', views.request_password_reset, name='request_password_reset'),
    path('password-reset-confirm/<uuid:token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('google/token/',views.google_login_token_view, name='google_login_token_view'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.CurrentUserView.as_view(), name='current-user'),
    path("profile/", ProfileView.as_view(), name="profile"),
    path('token_resfresh/',views.get_tokens_for_user, name='get_tokens_for_user'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("upload-profile-picture/", views.UploadProfilePictureView.as_view(), name="upload-profile-picture"),
    path('api/start-interview/', views.start_interview, name='start-interview'),
    path('submit_answer/', views.submit_answer, name='submit_answer'),
    path('get_interview_summary/', views.get_interview_summary, name='get_interview_summary'),
    #path('api/transcribe/', views.transcribe_audio, name='transcribe_audio'),
    #path('transcribe_and_save_answer/',views.transcribe_and_save_answer, name='transcribe_and_save_answer'),
    path('resume_analysis/', views.resume_analysis, name='resume_analysis'),
    path('get_or_create_courses/', views.get_or_create_courses, name='get_or_create_courses'),
    path('start_course/', views.start_course, name='start_course'),
    path('add_module/', views.add_module, name='add_module'),
    path('visualize_content/', views.visualize_content, name='visualize_content'),
    path('dashboard/',views.dashboard_data_view,name="dashboard_data_view"),
    path('profile_stats/', views.get_profile_stats_view, name='profile_stats'),
    path('gamification_profile/', views.get_gamification_profile, name='gamification_profile'),
    path('logincheck/', views.login_check, name='login-check'),

    # P2P Interview
    path('p2p/find_partner/', views.find_partner, name='find_partner'),
    path('p2p/poll_status/', views.poll_match_status, name='poll_match_status'),
    path('p2p/signal/', views.exchange_signal, name='exchange_signal'),
    path('p2p/ai_feedback/', views.p2p_ai_feedback, name='p2p_ai_feedback'),

]