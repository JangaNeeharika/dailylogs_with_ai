"""
logs/chat_service.py
──────────────────────────────────────────────────────────────────────────────
Builds the prompt/message list for each chatbot role and calls Ollama.

Two public functions:
    get_member_response(user, user_message, history)  → str
    get_mentor_response(user, user_message, history)  → str

Context is injected into the system prompt so the LLM always has
structured, up-to-date data from the DB — no hallucination risk.
"""

from datetime import date, timedelta
from django.db.models import Sum
from .ollama_service import chat


# ── System Prompts ────────────────────────────────────────────────────────────

_MEMBER_SYSTEM = """You are "Yours AI", the personal assistant inside a daily log tracking app.
You help the MEMBER understand their own work progress.

RESPONSE RULES — FOLLOW STRICTLY:
1. Always use structured markdown in your replies:
   - Use **bold** for important numbers or key terms.
   - Use bullet lists for multiple items.
   - Use tables when comparing data (e.g., logs by date).
   - Use ### headers to break long answers into sections.
2. Never produce walls of text. Keep paragraphs to 2–3 sentences max.
3. Answer ONLY using the context provided below. Never invent log entries, hours, or dates.
4. If the member asks something you can't answer from the data, say:
   "I don't have that information in your logs — try adding a log entry for that period."
5. For report generation requests, respond with exactly:
   TRIGGER_REPORT
   (the frontend will open the report wizard automatically)
6. Be warm and encouraging. Celebrate streaks and good work habits.

The member's data is injected below each message in a <context> block.
"""

_MENTOR_SYSTEM = """You are "Mentor AI", the team management assistant inside a daily log tracking app.
You help MENTORS oversee member activity, identify trends, and draft feedback.

RESPONSE RULES — FOLLOW STRICTLY:
1. Always use structured markdown:
   - Tables for comparing members (name | logs | hours | avg mark).
   - Bullet lists for action items or findings.
   - ### headers for multi-part answers.
2. Never produce walls of text.
3. Answer ONLY from the context data provided. Never invent member names, hours, or marks.
4. For underperformance queries: highlight members with < 3 logs in the past 7 days or avg mark < 3.
5. When asked to draft feedback/template messages, produce a polite, professional template the mentor can copy.
6. For report generation, respond with: TRIGGER_REPORT
7. Use a professional but approachable tone.

Member data is injected below each message in a <context> block.
"""


# ── Context Builders ──────────────────────────────────────────────────────────

def _build_member_context(user) -> str:
    """Serialize this member's logs and stats into a readable context block."""
    from .models import Log, Mark

    today      = date.today()
    week_start = today - timedelta(days=today.weekday())

    logs = list(
        Log.objects
           .filter(member=user)
           .select_related("mark")
           .order_by("-date")[:50]
    )

    total_logs  = len(logs)
    total_hours = sum(float(l.hours_spent or 0) for l in logs)
    week_logs   = [l for l in logs if l.date >= week_start]
    week_hours  = sum(float(l.hours_spent or 0) for l in week_logs)

    # streak
    streak, check = 0, today
    logged_dates  = {l.date for l in logs}
    while check in logged_dates:
        streak += 1
        check  -= timedelta(days=1)

    context = (
        f"### Member: {user.get_full_name() or user.username}\n"
        f"- Total logs: **{total_logs}**\n"
        f"- Total hours logged: **{total_hours:.1f}h**\n"
        f"- This week: **{len(week_logs)} logs**, **{week_hours:.1f}h**\n"
        f"- Current streak: **{streak} day(s)**\n"
        f"- Today's date: **{today}**\n\n"
        f"### Recent Log Entries (latest 50)\n"
    )

    if not logs:
        context += "_No logs found._\n"
    else:
        context += "| Date | Title | Hours | Tags | Mark |\n"
        context += "|------|-------|-------|------|------|\n"
        for l in logs:
            try:
                mark_str = f"⭐{l.mark.stars}/5"
                if l.mark.note:
                    mark_str += f" – {l.mark.note}"
            except Exception:
                mark_str = "—"
            desc = (l.description or "")[:80].replace("|", "｜")
            context += (
                f"| {l.date} | {l.title} ({desc}…) | "
                f"{l.hours_spent:.1f}h | {l.tags or '—'} | {mark_str} |\n"
            )

    return context


def _build_mentor_context(user) -> str:
    """Serialize all member summaries + recent logs for mentor view."""
    from django.contrib.auth.models import User as DjangoUser
    from .models import Log, Mark, Profile

    today      = date.today()
    week_start = today - timedelta(days=today.weekday())

    members = (
        DjangoUser.objects
                  .filter(profile__role="member")
                  .prefetch_related("logs", "logs__mark", "profile")
    )

    context = (
        f"### Mentor Dashboard Context\n"
        f"- Today: **{today}**\n\n"
        f"### Member Summary\n"
        f"| Member | Total Logs | Total Hours | This Week | Avg Mark |\n"
        f"|--------|-----------|-------------|-----------|----------|\n"
    )

    member_details = []
    for m in members:
        logs      = list(m.logs.all())
        t_hours   = sum(float(l.hours_spent or 0) for l in logs)
        w_logs    = [l for l in logs if l.date >= week_start]
        w_hours   = sum(float(l.hours_spent or 0) for l in w_logs)
        marked    = [l for l in logs if hasattr(l, "mark") and l.mark_id]
        avg_mark  = (sum(l.mark.stars for l in marked) / len(marked)) if marked else 0
        college   = getattr(getattr(m, "profile", None), "college", "—")

        context += (
            f"| {m.get_full_name() or m.username} | {len(logs)} | "
            f"{t_hours:.1f}h | {len(w_logs)} logs / {w_hours:.1f}h | "
            f"{'⭐'+str(round(avg_mark,1)) if marked else '—'} |\n"
        )
        member_details.append({
            "name":      m.get_full_name() or m.username,
            "week_logs": len(w_logs),
            "avg_mark":  avg_mark,
            "college":   college,
        })

    # Flag underperformers
    underperformers = [
        m for m in member_details
        if m["week_logs"] < 3 or (m["avg_mark"] > 0 and m["avg_mark"] < 3)
    ]
    if underperformers:
        context += "\n### ⚠️ Members Needing Attention (< 3 logs/week OR avg mark < 3)\n"
        for m in underperformers:
            context += f"- **{m['name']}** — {m['week_logs']} log(s) this week, avg mark: {m['avg_mark']:.1f}\n"

    # Recent 30 logs across all members
    recent_logs = (
        Log.objects
           .filter(member__profile__role="member")
           .select_related("member")
           .order_by("-date", "-created_at")[:30]
    )
    context += "\n### Recent Logs (All Members, latest 30)\n"
    context += "| Date | Member | Title | Hours |\n"
    context += "|------|--------|-------|-------|\n"
    for l in recent_logs:
        name = l.member.get_full_name() or l.member.username
        context += f"| {l.date} | {name} | {l.title} | {l.hours_spent:.1f}h |\n"

    return context


# ── Public Interface ──────────────────────────────────────────────────────────

def _build_messages(system_prompt: str, context: str, history: list, user_message: str) -> list:
    """
    Assemble the messages list for Ollama chat.
    Injects context into every user message so the model always has fresh data.
    """
    messages = [{"role": "system", "content": system_prompt}]

    # Chat history (last 10 turns, oldest first)
    for h in history:
        messages.append({"role": h.role, "content": h.message})

    # Current user message with injected context
    messages.append({
        "role": "user",
        "content": (
            f"{user_message}\n\n"
            f"<context>\n{context}\n</context>"
        ),
    })
    return messages


def get_member_response(user, user_message: str, history) -> str:
    """
    Build member context + call Ollama. Returns the assistant reply string.
    `history` is a QuerySet of ChatMessage objects (ordered oldest→newest).
    """
    context  = _build_member_context(user)
    messages = _build_messages(_MEMBER_SYSTEM, context, history, user_message)
    return chat(messages)


def get_mentor_response(user, user_message: str, history) -> str:
    """
    Build mentor context + call Ollama. Returns the assistant reply string.
    """
    context  = _build_mentor_context(user)
    messages = _build_messages(_MENTOR_SYSTEM, context, history, user_message)
    return chat(messages)