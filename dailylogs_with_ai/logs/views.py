import json
from datetime import timedelta, date

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_GET

from .models import Profile, Log, Mark


from .ollama_service import generate_ai_report


def generate_report(request):
    log_text = "Your logs data here"

    summary = generate_ai_report(log_text)

    return JsonResponse({
        "summary": summary
    })
# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

MEMBER_COLORS = [
    '#3a6b4d', '#2d5fa0', '#7b4fa0', '#b5451b',
    '#c98b2a', '#1a7a7a', '#8b3a8b', '#c44a38',
]

def _assign_color(username):
    h = 0
    for c in username:
        h = (h * 31 + ord(c)) % len(MEMBER_COLORS)
    return MEMBER_COLORS[h]


def _calc_streak(user):
    """Count consecutive days (ending today) with at least one log."""
    today = date.today()
    streak = 0
    check = today
    while True:
        if Log.objects.filter(member=user, date=check).exists():
            streak += 1
            check -= timedelta(days=1)
        else:
            break
    return streak


def _json_body(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ─────────────────────────────────────────
# Auth Pages
# ─────────────────────────────────────────

@ensure_csrf_cookie
def login_page(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)
    return render(request, 'logs/login.html')


def _redirect_by_role(user):
    try:
        role = user.profile.role
    except Profile.DoesNotExist:
        role = 'member'
    if role == 'mentor':
        return redirect('mentor_dashboard')
    return redirect('member_dashboard')


@require_POST
def login_view(request):
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    role     = request.POST.get('role', '')

    user = authenticate(request, username=username, password=password)
    if user is None:
        messages.error(request, 'Invalid username or password.')
        return redirect('login')

    try:
        profile_role = user.profile.role
    except Profile.DoesNotExist:
        profile_role = 'member'

    if role and profile_role != role:
        messages.error(request, f'This account is registered as a {profile_role}, not {role}.')
        return redirect('login')

    login(request, user)
    return _redirect_by_role(user)


@require_POST
def signup_view(request):
    username = request.POST.get('username', '').strip()
    email    = request.POST.get('email', '').strip()
    college  = request.POST.get('college', '').strip()
    password = request.POST.get('password', '')
    role     = request.POST.get('role', '')

    if User.objects.filter(username=username).exists():
        messages.error(request, 'Username already taken. Please choose another.')
        return redirect('login')

    user = User.objects.create_user(username=username, email=email, password=password)
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.role    = role
    profile.college = college
    profile.save()

    messages.success(request, 'Account created! Please log in.')
    return redirect('login')


def logout_view(request):
    logout(request)
    return redirect('login')


# ─────────────────────────────────────────
# Dashboard Pages
# ─────────────────────────────────────────

@login_required(login_url='login')
def member_dashboard(request):
    try:
        role = request.user.profile.role
    except Profile.DoesNotExist:
        role = 'member'
    if role != 'member':
        return redirect('mentor_dashboard')
    return render(request, 'logs/member_dashboard.html', {'username': request.user.username})


# FIX 1: @login_required was on a separate line, detached from the function.
# FIX 2: Removed the duplicate member_dashboard definition at the bottom of the file.
@login_required(login_url='login')
def mentor_dashboard(request):
    try:
        role = request.user.profile.role
    except Profile.DoesNotExist:
        role = 'member'
    if role != 'mentor':
        return redirect('member_dashboard')
    return render(request, 'logs/mentor_dashboard.html')


# ─────────────────────────────────────────
# API – shared CSRF
# ─────────────────────────────────────────

@ensure_csrf_cookie
def csrf_view(request):
    from django.middleware.csrf import get_token
    return JsonResponse({'csrftoken': get_token(request)})


# ─────────────────────────────────────────
# API – Member endpoints
# ─────────────────────────────────────────

@login_required(login_url='login')
@require_GET
def api_me(request):
    user = request.user
    try:
        color = user.profile.color
    except Profile.DoesNotExist:
        color = '#3a6b4d'
    return JsonResponse({
        'id':       user.id,
        'username': user.username,
        'name':     user.get_full_name() or user.username,
        'color':    color,
    })


@login_required(login_url='login')
@require_GET
def api_stats(request):
    user  = request.user
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    total      = Log.objects.filter(member=user).count()
    week_logs  = Log.objects.filter(member=user, date__gte=week_start)
    week_count = week_logs.count()
    week_hours = week_logs.aggregate(h=Sum('hours_spent'))['h'] or 0
    streak     = _calc_streak(user)

    return JsonResponse({
        'total':      total,
        'week_count': week_count,
        'week_hours': round(week_hours, 1),
        'streak':     streak,
    })


@login_required(login_url='login')
@require_GET
def api_my_logs(request):
    logs = Log.objects.filter(member=request.user).order_by('-date', '-created_at')
    data = []
    for l in logs:
        try:
            mark = {'stars': l.mark.stars, 'note': l.mark.note}
        except Mark.DoesNotExist:
            mark = None
        data.append({
            'id':          l.id,
            'date':        str(l.date),
            'title':       l.title,
            'description': l.description,
            'hours_spent': l.hours_spent,
            'tags':        l.tags,
            'created_at':  l.created_at.isoformat(),
            'mark':        mark,
        })
    return JsonResponse(data, safe=False)


@login_required(login_url='login')
def api_add_log(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data        = _json_body(request)
    log_date    = data.get('date') or str(date.today())
    title       = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    hours_spent = float(data.get('hours_spent') or 0)
    tags        = (data.get('tags') or '').strip()

    if not title:
        return JsonResponse({'error': 'Title is required.'}, status=400)

    log = Log.objects.create(
        member      = request.user,
        date        = log_date,
        title       = title,
        description = description,
        hours_spent = hours_spent,
        tags        = tags,
    )
    return JsonResponse({
        'success': True,
        'log': {
            'id':          log.id,
            'date':        str(log.date),
            'title':       log.title,
            'description': log.description,
            'hours_spent': log.hours_spent,
            'tags':        log.tags,
            'created_at':  log.created_at.isoformat(),
        }
    }, status=201)


@login_required(login_url='login')
def api_update_log(request, log_id):
    if request.method not in ('PUT', 'PATCH'):
        return JsonResponse({'error': 'PUT or PATCH required'}, status=405)

    try:
        log = Log.objects.get(pk=log_id, member=request.user)
    except Log.DoesNotExist:
        return JsonResponse({'error': 'Log not found'}, status=404)

    data        = _json_body(request)
    log_date    = data.get('date') or str(log.date)
    title       = (data.get('title') or '').strip()
    description = (data.get('description') or '').strip()
    hours_spent = float(data.get('hours_spent') or 0)
    tags        = (data.get('tags') or '').strip()

    if not title:
        return JsonResponse({'error': 'Title is required.'}, status=400)

    log.date        = log_date
    log.title       = title
    log.description = description
    log.hours_spent = hours_spent
    log.tags        = tags
    log.save()

    return JsonResponse({
        'success': True,
        'log': {
            'id':          log.id,
            'date':        str(log.date),
            'title':       log.title,
            'description': log.description,
            'hours_spent': log.hours_spent,
            'tags':        log.tags,
            'created_at':  log.created_at.isoformat(),
        }
    })


@login_required(login_url='login')
@require_GET
def api_team_logs(request):
    since = timezone.now() - timedelta(hours=24)
    logs  = (Log.objects
             .filter(created_at__gte=since)
             .exclude(member=request.user)
             .select_related('member', 'member__profile')
             .order_by('-created_at'))
    data = []
    for l in logs:
        try:
            color = l.member.profile.color
        except Profile.DoesNotExist:
            color = _assign_color(l.member.username)
        data.append({
            'id':           l.id,
            'member_name':  l.member.get_full_name() or l.member.username,
            'member_color': color,
            'date':         str(l.date),
            'title':        l.title,
            'description':  l.description,
            'hours_spent':  l.hours_spent,
            'tags':         l.tags,
            'created_at':   l.created_at.isoformat(),
        })
    return JsonResponse(data, safe=False)


# ─────────────────────────────────────────
# API – Mentor endpoints
# ─────────────────────────────────────────

@login_required(login_url='login')
@require_GET
def api_mentor_stats(request):
    members     = User.objects.filter(profile__role='member')
    total_logs  = Log.objects.filter(member__in=members)
    total_hours = total_logs.aggregate(h=Sum('hours_spent'))['h'] or 0
    today_count = total_logs.filter(date=date.today()).count()

    return JsonResponse({
        'members':     members.count(),
        'total':       total_logs.count(),
        'total_hours': round(total_hours, 1),
        'today':       today_count,
    })


@login_required(login_url='login')
@require_GET
def api_members(request):
    members = (User.objects
               .filter(profile__role='member')
               .prefetch_related('logs', 'logs__mark', 'profile'))
    data = []
    for m in members:
        logs      = list(m.logs.all())
        total_hrs = sum(l.hours_spent for l in logs)
        marked    = [l for l in logs if hasattr(l, 'mark')]
        avg_stars = (sum(l.mark.stars for l in marked) / len(marked)) if marked else 0
        try:
            color   = m.profile.color
            college = m.profile.college
        except Profile.DoesNotExist:
            color   = _assign_color(m.username)
            college = ''

        data.append({
            'id':          m.id,
            'username':    m.username,
            'name':        m.get_full_name() or m.username,
            'color':       color,
            'college':     college,
            'entries':     len(logs),
            'total_hours': round(total_hrs, 1),
            'avg_mark':    round(avg_stars, 1),
            'marked':      len(marked),
        })
    return JsonResponse(data, safe=False)


@login_required(login_url='login')
@require_GET
def api_all_logs(request):
    logs = (
        Log.objects
        .filter(member__profile__role='member')
        .select_related('member', 'member__profile')
        .order_by('-date', '-created_at')
    )
    data = []
    for l in logs:
        profile  = getattr(l.member, 'profile', None)
        color    = profile.color if profile else '#3a6b4d'
        mark_obj = Mark.objects.filter(log=l).first()
        mark     = {'stars': mark_obj.stars, 'note': mark_obj.note} if mark_obj else None

        data.append({
            'id':           l.id,
            'member_id':    l.member.id,          # ← used by JS to link entries → members
            'member_name':  l.member.get_full_name() or l.member.username,
            'member_color': color,
            'date':         str(l.date),
            'title':        l.title,
            'description':  l.description,
            'hours_spent':  l.hours_spent,
            'tags':         l.tags,
            'created_at':   l.created_at.isoformat(),
            'mark':         mark,
        })
    return JsonResponse(data, safe=False)


@login_required(login_url='login')
def api_save_mark(request, log_id):
    if request.method not in ('POST', 'PUT', 'PATCH'):
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        log = Log.objects.get(pk=log_id)
    except Log.DoesNotExist:
        return JsonResponse({'error': 'Log not found'}, status=404)

    data  = _json_body(request)
    stars = int(data.get('stars', 0))
    note  = (data.get('note') or '').strip()

    if not 1 <= stars <= 5:
        return JsonResponse({'error': 'Stars must be 1-5'}, status=400)

    mark, _ = Mark.objects.update_or_create(
        log=log,
        defaults={'mentor': request.user, 'stars': stars, 'note': note}
    )
    return JsonResponse({'success': True, 'stars': mark.stars, 'note': mark.note})


@login_required(login_url='login')
def api_delete_mark(request, log_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    Mark.objects.filter(log_id=log_id).delete()
    return JsonResponse({'success': True})


@login_required(login_url='login')
@require_GET
def api_member_logs(request, member_id):
    try:
        target = User.objects.get(pk=member_id, profile__role='member')
    except User.DoesNotExist:
        return JsonResponse({'error': 'Member not found'}, status=404)

    logs = Log.objects.filter(member=target).select_related('mark').order_by('-date')
    data = []
    for l in logs:
        try:
            mark = {'stars': l.mark.stars, 'note': l.mark.note}
        except Mark.DoesNotExist:
            mark = None
        data.append({
            'id':          l.id,
            'date':        str(l.date),
            'title':       l.title,
            'description': l.description,
            'hours_spent': l.hours_spent,
            'tags':        l.tags,
            'created_at':  l.created_at.isoformat(),
            'mark':        mark,
        })
    return JsonResponse(data, safe=False)



# ─────────────────────────────────────────────────────────────
# ADD THESE IMPORTS at the top of your logs/views.py
# (merge with any imports already there)
# ─────────────────────────────────────────────────────────────
import random
import json
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
import datetime

# ─────────────────────────────────────────────────────────────
# Simple in-memory OTP store  →  replace with a DB model in
# production so it survives server restarts.
# Format:  { email: {'otp': '123456', 'expires': datetime} }
# ─────────────────────────────────────────────────────────────
_otp_store = {}


# ─────────────────────────────────────────────────────────────
# 1.  FORGOT PASSWORD – Step 1: Send OTP
# ─────────────────────────────────────────────────────────────
@require_POST
def forgot_send_otp(request):
    email = request.POST.get('email', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Check the email exists in the system
    if not User.objects.filter(email=email).exists():
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'No account found with this email.'})
        messages.error(request, 'No account found with this email.')
        return redirect('/?panel=forgot')

    # Generate a 6-digit OTP
    otp = str(random.randint(100000, 999999))
    expires = timezone.now() + datetime.timedelta(minutes=10)
    _otp_store[email] = {'otp': otp, 'expires': expires}

    # Send email
    try:
        send_mail(
            subject='Daily Logs – Password Reset OTP',
            message=(
                f'Your OTP for password reset is: {otp}\n\n'
                f'This code is valid for 10 minutes.\n'
                f'If you did not request this, ignore this email.'
            ),
            from_email=None,          # uses DEFAULT_FROM_EMAIL from settings.py
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception as e:
        
        print("EMAIL ERROR:", e) 
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Failed to send email. Try again.'})
        messages.error(request, 'Failed to send email. Try again.')
        return redirect('/?panel=forgot')

    if is_ajax:
        return JsonResponse({'success': True})

    # Non-JS fallback: redirect back to page showing step 2
    return redirect(f'/?panel=forgot&step=2&email={email}')


# ─────────────────────────────────────────────────────────────
# 2.  FORGOT PASSWORD – Step 2: Verify OTP + Reset Password
# ─────────────────────────────────────────────────────────────
@require_POST
def forgot_verify_otp(request):
    email       = request.POST.get('email', '').strip()
    otp_input   = request.POST.get('otp', '').strip()
    new_password    = request.POST.get('new_password', '')
    confirm_password = request.POST.get('confirm_password', '')

    # Basic validations
    if new_password != confirm_password:
        messages.error(request, 'Passwords do not match.')
        return redirect(f'/?panel=forgot&step=2&email={email}')

    record = _otp_store.get(email)
    if not record:
        messages.error(request, 'OTP expired or not requested. Please try again.')
        return redirect('/?panel=forgot')

    if timezone.now() > record['expires']:
        _otp_store.pop(email, None)
        messages.error(request, 'OTP has expired. Please request a new one.')
        return redirect('/?panel=forgot')

    if record['otp'] != otp_input:
        messages.error(request, 'Invalid OTP. Please try again.')
        return redirect(f'/?panel=forgot&step=2&email={email}')

    # OTP is valid – update password
    try:
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        _otp_store.pop(email, None)
        messages.success(request, 'Password reset successful! Please log in.')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')

    return redirect('/')


# ─────────────────────────────────────────────────────────────
# 3.  CHANGE PASSWORD (requires old password)
# ─────────────────────────────────────────────────────────────
@require_POST
def change_password(request):
    username         = request.POST.get('username', '').strip()
    old_password     = request.POST.get('old_password', '')
    new_password     = request.POST.get('new_password', '')
    confirm_password = request.POST.get('confirm_password', '')

    if new_password != confirm_password:
        messages.error(request, 'New passwords do not match.')
        return redirect('/?panel=change')

    # Verify old credentials
    user = authenticate(request, username=username, password=old_password)
    if user is None:
        messages.error(request, 'Incorrect username or current password.')
        return redirect('/?panel=change')

    user.set_password(new_password)
    user.save()
    messages.success(request, 'Password changed successfully! Please log in.')
    return redirect('/')


# ─────────────────────────────────────────────────────────────
# AI – Report Generation (Member Dashboard)
# ─────────────────────────────────────────────────────────────
from datetime import datetime as _dt


def _parse_date(s):
    return _dt.strptime(s, '%Y-%m-%d').date()


def _missing_dates_in_range(user, start_date, end_date):
    """Return a list of date objects in [start_date, end_date] that have no log."""
    logged_dates = set(
        Log.objects.filter(member=user, date__range=[start_date, end_date])
        .values_list('date', flat=True)
    )
    missing = []
    d = start_date
    while d <= end_date:
        if d not in logged_dates:
            missing.append(d)
        d += timedelta(days=1)
    return missing


@login_required(login_url='login')
def api_report_check(request):
    """
    Step 1: Member submits a from/to date range.
    Returns the dates within that range that have NO log entry,
    so the frontend can ask the member for a reason for each.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    try:
        start_date = _parse_date(data.get('start_date', ''))
        end_date   = _parse_date(data.get('end_date', ''))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid or missing dates (use YYYY-MM-DD).'}, status=400)

    if start_date > end_date:
        return JsonResponse({'error': '"From" date must be before "To" date.'}, status=400)

    if (end_date - start_date).days > 60:
        return JsonResponse({'error': 'Please choose a range of 60 days or less.'}, status=400)

    missing = _missing_dates_in_range(request.user, start_date, end_date)

    return JsonResponse({
        'start_date': str(start_date),
        'end_date':   str(end_date),
        'missing_dates': [str(d) for d in missing],
    })


@login_required(login_url='login')
def api_report_generate(request):
    """
    Step 2: Member submits the date range + reasons for any missing dates.
    Calls the AI to generate the summary report.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = _json_body(request)
    try:
        start_date = _parse_date(data.get('start_date', ''))
        end_date   = _parse_date(data.get('end_date', ''))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid or missing dates (use YYYY-MM-DD).'}, status=400)

    if start_date > end_date:
        return JsonResponse({'error': '"From" date must be before "To" date.'}, status=400)

    missing_reasons = data.get('missing_reasons') or {}   # { "YYYY-MM-DD": "reason text" }
    feedback = (data.get('feedback') or '').strip() or None

    logs = list(
        Log.objects.filter(member=request.user, date__range=[start_date, end_date])
        .order_by('date')
    )
    missing_dates = _missing_dates_in_range(request.user, start_date, end_date)
    try:
        log_text = f"""
    Report period: {start_date} to {end_date}

    User feedback:
    {feedback or "None"}

    Missing dates and reasons:
    """

        for d in missing_dates:
            reason = missing_reasons.get(str(d), "No reason provided")
            log_text += f"\n- {d}: {reason}"

        log_text += "\n\nLogs:\n"

        for log in logs:
            log_text += (
                f"\nDate: {log.date}"
                f"\nDescription: {log.description}"
                f"\nHours Spent: {log.hours_spent}\n"
            )

        report_text = generate_ai_report(log_text)

    except Exception as e:
        return JsonResponse(
            {'error': f'AI request failed: {e}'},
            status=502
        )

    return JsonResponse({
        'success': True,
        'report': report_text,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'missing_dates': [str(d) for d in missing_dates],
   })
import json
import ollama
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings

# Helper function to query local Ollama instance
def get_chat_response(system_prompt, user_message, chat_history=None):
    if chat_history is None:
        chat_history = []
        
    # Build structural message payload
    messages = [{"role": "system", "content": system_prompt}]
    
    # Append past conversation history if any exists
    for msg in chat_history:
        messages.append({"role": msg.get("role"), "content": msg.get("content")})
        
    messages.append({"role": "user", "content": user_message})
    
    model_name = getattr(settings, 'OLLAMA_MODEL', 'llama3')
    
    try:
        response = ollama.chat(model=model_name, messages=messages)
        return response['message']['content']
    except Exception as e:
        return f"Error connecting to Ollama engine: {str(e)}"

@csrf_exempt
@login_required
def member_chatbot_api(request):
    """Structured Chatbot for the Member Dashboard"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
        
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "")
        history = data.get("history", []) # Array of objects: [{"role": "user", "content": "hi"}]
        
        system_prompt = (
            "You are 'Yours AI Chatbot', a highly structured assistant inside the Member Dashboard. "
            "Your job is to assist members with account status, profile tracking, goals, and daily logs. "
            "Always format your outputs beautifully using markdown bullet points, short lists, or tables. "
            "If the member asks to generate a report, tell them: 'To generate your official progress report, "
            "please use the dedicated Report Generator module button on your dashboard layout.'"
        )
        
        reply = get_chat_response(system_prompt, user_message, history)
        return JsonResponse({"reply": reply})
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@login_required
def mentor_chatbot_api(request):
    """Structured Chatbot for the Mentor Dashboard"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
        
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "")
        history = data.get("history", [])
        
        system_prompt = (
            "You are 'Yours AI Chatbot' tailored for the Mentor Dashboard. "
            "Your job is to help mentors manage student overviews, evaluate daily logs, flag underperforming students, "
            "and assist with schedule workflows. "
            "Always format your text cleanly using bold indicators and markdown structures. "
            "If the mentor commands you to pull or generate a report, instruct them to invoke the integrated "
            "Report Generator utility built into their top dashboard navbar panel."
        )
        
        reply = get_chat_response(system_prompt, user_message, history)
        return JsonResponse({"reply": reply})
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@login_required
def api_clear_chat(request):
    """Resets the chat context history for the active session"""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
    
    try:
        # Clear chat session keys if stored in Django sessions
        if 'chat_history' in request.session:
            del request.session['chat_history']
            request.session.modified = True
            
        return JsonResponse({"status": "success", "message": "Chat history cleared successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
import json
import ollama
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from django.apps import apps
from django.conf import settings

def get_chat_response(system_prompt, user_message, chat_history=None):
    if chat_history is None:
        chat_history = []
    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        messages.append({"role": msg.get("role"), "content": msg.get("content")})
    messages.append({"role": "user", "content": user_message})
    
    try:
        client = ollama.Client(host='http://127.0.0.1:11434')
        response = client.chat(model='llama3', messages=messages) 
        return response['message']['content']
    except Exception as e:
        print(f"\n[OLLAMA SYSTEM ERROR]: {str(e)}\n")
        return None
@csrf_exempt
@login_required
def member_chatbot_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)
        
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "")
        history = data.get("history", [])
        frontend_logs = data.get("frontend_logs", []) # Grab context directly from frontend
        
        log_context = ""
        lowered_message = user_message.lower()
        
        # Build prompt context utilizing the frontend log parameters array
        if any(word in lowered_message for word in ["summary", "log", "work"]):
            if frontend_logs:
                log_context = "\nHere are the user's real log entries for this week:\n"
                for index, log in enumerate(frontend_logs, 1):
                    # Handle if log entries are objects or primitive strings
                    log_text = log.get('content') or log.get('text') if isinstance(log, dict) else str(log)
                    log_context += f"{index}. {log_text}\n"
            else:
                log_context = "\n(System Note: No recent log dashboard logs were detected in user application memory.)\n"

        system_prompt = (
            "You are 'Yours AI Chatbot' inside the Member Dashboard. "
            "Help members track progress and evaluate daily metrics. "
            f"{log_context}"
            "Always format your outputs with clean markdown bullet points, bold indicators, and short lists. "
            "If logs are available, summarize them concisely. If none are provided, advise them to complete logs."
        )
        
        # Execute Ollama Call
        client = ollama.Client(host='http://127.0.0.1:11434')
        
        # Build history payloads cleanly
        ollama_messages = [{"role": "system", "content": system_prompt}]
        for item in history:
            ollama_messages.append({"role": item.get("role"), "content": item.get("content")})
        ollama_messages.append({"role": "user", "content": user_message})
        
        response = client.chat(model='llama3', messages=ollama_messages)
        return JsonResponse({"reply": response['message']['content']})
        
    except Exception as e:
        print(f"\n[BACKEND CHAT ERROR]: {str(e)}\n")
        return JsonResponse({"reply": f"⚠️ **Backend Exception Error:** `{str(e)}`"}, status=200)


"""
======================================================================
ADD THESE VIEW FUNCTIONS TO YOUR EXISTING views.py
======================================================================
Make sure these imports are at the top of your views.py:

    import json
    from django.http import JsonResponse
    from django.views.decorators.http import require_POST
    from django.contrib.auth.decorators import login_required
    from .ai_service import (
        get_member_chat_response,
        get_mentor_chat_response,
        suggest_log_description,
    )

And import your models as needed (DailyLog, Member, Mentor, etc.)
======================================================================
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

# ── adjust these imports to match your actual model/app names ──────────────
from .models import Log # change if needed
from .ai_service import (
    get_member_chat_response,
    get_mentor_chat_response,
    suggest_log_description,
)
# ──────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# MEMBER CHATBOT ENDPOINT
# ---------------------------------------------------------------------------

@require_POST
@login_required
def member_chatbot(request):
    """
    POST /chatbot/member/
    Body: { "message": "..." }
    Returns: { "reply": "..." }

    The chatbot is aware of the logged-in member's recent 10 logs.
    """
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"error": "Message cannot be empty."}, status=400)

        # ── Get current member ──────────────────────────────────────────
        # Adjust this depending on how your Member model links to User.
        # Option A: if Member has a OneToOne to User:
        try:
            member = Member.objects.get(user=request.user)
            member_name = member.name  # or member.user.get_full_name() or member.username
        except Member.DoesNotExist:
            member_name = request.user.get_full_name() or request.user.username
            member = None

        # ── Build logs context ──────────────────────────────────────────
        logs_qs = (
            DailyLog.objects
            .filter(member=member)
            .order_by("-date")[:10]
            if member
            else DailyLog.objects.none()
        )

        logs_context = [
            {
                "date": str(log.date),
                "title": log.title,
                "description": log.description or "",
                "mood": log.mood if hasattr(log, "mood") else "N/A",
                "hours_worked": str(log.hours_worked) if hasattr(log, "hours_worked") else "N/A",
            }
            for log in logs_qs
        ]

        reply = get_member_chat_response(user_message, member_name, logs_context)
        return JsonResponse({"reply": reply})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Something went wrong: {str(e)}"}, status=500)


# ---------------------------------------------------------------------------
# MENTOR CHATBOT ENDPOINT
# ---------------------------------------------------------------------------

"""
======================================================================
REPLACE your mentor_chatbot view in views.py with this fixed version.

The error "name 'Mentor' is not defined" means either:
  - Your Mentor model is not imported at the top of views.py
  - OR your model is named differently (e.g. MentorProfile, UserProfile)

This version uses request.user directly and finds team members via
the Member model's foreign key to the logged-in user.

ADJUST the model names marked with ← CHANGE THIS to match your project.
======================================================================
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

# ─── CHANGE THESE IMPORTS to match your actual models ──────────────────────
# Look at your models.py and find the correct class names.
# Common patterns:
#   from .models import DailyLog, Member
#   from logs.models import DailyLog, Member
#   from accounts.models import Member
#
# The key thing: you DON'T need a separate Mentor model if mentors are just
# User objects with a role. This view uses request.user directly.
# ──────────────────────────────────────────────────────────────────────────

from .ai_service import get_mentor_chat_response  # keep this


@require_POST
@login_required
def mentor_chatbot(request):
    """
    Fixed mentor chatbot that doesn't crash if Mentor model doesn't exist.
    It uses request.user as the mentor and fetches all team logs.
    """
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"error": "Message cannot be empty."}, status=400)

        # ── Mentor name from the logged-in user ─────────────────────────
        mentor_name = request.user.get_full_name() or request.user.username

        # ── Fetch team logs ─────────────────────────────────────────────
        # Try different approaches depending on your model structure.
        # UNCOMMENT whichever matches your project:

        # ── APPROACH A: If Member has a ForeignKey to Mentor model ──────
        # from .models import Member, DailyLog  ← uncomment and adjust
        # try:
        #     from .models import Mentor as MentorModel
        #     mentor_obj = MentorModel.objects.get(user=request.user)
        #     members = Member.objects.filter(mentor=mentor_obj)
        # except Exception:
        #     members = Member.objects.all()
        # logs_qs = DailyLog.objects.filter(member__in=members).select_related("member").order_by("-date")[:30]

        # ── APPROACH B (DEFAULT): Get all logs — works for small teams ──
        # Replace DailyLog with your actual log model name
        try:
            from .models import Log  # ← CHANGE 'DailyLog' if your model has a different name
            logs_qs = Log.objects.select_related("member").order_by("-date")[:30]

            team_context = []
            for log in logs_qs:
                try:
                    # Try different ways to get the member name — use whichever works
                    member = log.member
                    if hasattr(member, "name"):
                        mname = member.name
                    elif hasattr(member, "user"):
                        mname = member.user.get_full_name() or member.user.username
                    elif hasattr(member, "username"):
                        mname = member.username
                    else:
                        mname = str(member)

                    team_context.append({
                        "member_name": mname,
                        "log_date": str(log.date),
                        "title": log.title if hasattr(log, "title") else "",
                        "description": (log.description or "")[:120] if hasattr(log, "description") else "",
                        "mood": str(log.mood) if hasattr(log, "mood") else "N/A",
                        "hours_worked": str(log.hours_worked) if hasattr(log, "hours_worked") else "N/A",
                    })
                except Exception:
                    continue

        except ImportError:
            # If DailyLog import fails, return helpful message
            return JsonResponse({
                "reply": "⚠️ Could not load team logs. Check that 'DailyLog' is the correct model name in views.py."
            })

        reply = get_mentor_chat_response(user_message, mentor_name, team_context)
        return JsonResponse({"reply": reply})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"reply": f"⚠️ Error: {str(e)}. Check your model names in views.py."})


@require_POST
@login_required
def member_chatbot(request):
    """
    Fixed member chatbot. Uses request.user to find the member.
    """
    from .ai_service import get_member_chat_response

    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"error": "Message cannot be empty."}, status=400)

        member_name = request.user.get_full_name() or request.user.username
        logs_context = []

        try:
            from .models import Log, Member  # ← CHANGE if needed

            try:
                member = Member.objects.get(user=request.user)
            except Exception:
                member = None

            if member:
                logs_qs = Log.objects.filter(member=member).order_by("-date")[:10]
                if hasattr(member, "name"):
                    member_name = member.name
            else:
                logs_qs = Log.objects.none()

            for log in logs_qs:
                logs_context.append({
                    "date": str(log.date),
                    "title": log.title if hasattr(log, "title") else "",
                    "description": (log.description or "")[:120] if hasattr(log, "description") else "",
                    "mood": str(log.mood) if hasattr(log, "mood") else "N/A",
                    "hours_worked": str(log.hours_worked) if hasattr(log, "hours_worked") else "N/A",
                })

        except ImportError:
            pass  # No logs context — AI will still respond generally

        reply = get_member_chat_response(user_message, member_name, logs_context)
        return JsonResponse({"reply": reply})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"reply": f"⚠️ Error: {str(e)}. Check your model names in views.py."})


@require_POST
@login_required
def ai_suggest_log_description(request):
    """
    POST /logs/suggest-description/
    Body: { "title": "...", "mood": "...", "hours": "..." }
    Returns: { "title": "...", "tags": "...", "description": "..." }

    Called from the Add Log form when the user clicks "✨ Suggest Description".
    """
    from .ai_service import suggest_log_description

    try:
        data = json.loads(request.body)
        title = data.get("title", "").strip()
        mood = data.get("mood", "").strip()
        hours = data.get("hours", "").strip()

        if not title:
            return JsonResponse(
                {"error": "Please enter a log title first before generating a suggestion."},
                status=400,
            )

        member_name = request.user.get_full_name() or request.user.username

        suggestion = suggest_log_description(title, mood, hours, member_name)
        return JsonResponse(suggestion)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Something went wrong: {str(e)}"}, status=500)