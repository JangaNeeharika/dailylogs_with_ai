from django.urls import path
from . import views

urlpatterns = [
    # ── Pages ──────────────────────────────────────────────
    path('',               views.login_page,       name='login'),
    path('login/',         views.login_view,        name='login_post'),   # POST handler
    path('signup/',        views.signup_view,       name='signup'),
    path('logout/',        views.logout_view,       name='logout'),
    path('dashboard/',     views.member_dashboard,  name='member_dashboard'),
    path('mentor/',        views.mentor_dashboard,  name='mentor_dashboard'),

    # ── Shared API ─────────────────────────────────────────
    path('api/csrf/',      views.csrf_view,         name='api_csrf'),
    path('api/me/',        views.api_me,             name='api_me'),

    # ── Member API ─────────────────────────────────────────
    path('api/stats/',          views.api_stats,        name='api_stats'),
    path('api/logs/my/',        views.api_my_logs,       name='api_my_logs'),
    path('api/logs/add/',       views.api_add_log,       name='api_add_log'),
    path('api/logs/update/<int:log_id>/', views.api_update_log, name='api_update_log'),
    path('api/logs/team/24h/',  views.api_team_logs,     name='api_team_logs'),

    # ── AI Report Generation ────────────────────────────────
    path('api/report/check/',    views.api_report_check,    name='api_report_check'),
    path('api/report/generate/', views.api_report_generate, name='api_report_generate'),

    # ── Mentor API ─────────────────────────────────────────
    path('api/mentor/stats/',           views.api_mentor_stats,  name='api_mentor_stats'),
    path('api/mentor/members/',         views.api_members,       name='api_members'),
    path('api/mentor/logs/',            views.api_all_logs,      name='api_all_logs'),
    path('api/mentor/members/<int:member_id>/logs/', views.api_member_logs, name='api_member_logs'),
    path('api/mentor/mark/<int:log_id>/',   views.api_save_mark,   name='api_save_mark'),
    path('api/mentor/mark/<int:log_id>/delete/', views.api_delete_mark, name='api_delete_mark'),
    path('member-dashboard/', views.member_dashboard, name='member_dashboard'),

path('mentor/', views.mentor_dashboard, name='mentor_dashboard'),

# urls.py
path('forgot/send-otp/',  views.forgot_send_otp,  name='forgot_send_otp'),
path('forgot/verify-otp/', views.forgot_verify_otp, name='forgot_verify_otp'),
path('change-password/', views.change_password,   name='change_password'),


    path('api/chatbot/member/',  views.member_chatbot_api, name='member_chatbot_api'),
    path('api/chatbot/mentor/',  views.mentor_chatbot_api, name='mentor_chatbot_api'),
    path('api/chatbot/clear/',   views.api_clear_chat,     name='api_clear_chat'),
     path("chatbot/member/", views.member_chatbot, name="member_chatbot"),
    path("chatbot/mentor/", views.mentor_chatbot, name="mentor_chatbot"),
 
    # ── NEW: AI log description suggestion ─────────────────────────────
    path("logs/suggest-description/", views.ai_suggest_log_description, name="ai_suggest_log_description"),
]