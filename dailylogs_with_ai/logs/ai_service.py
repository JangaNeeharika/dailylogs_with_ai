import requests
import json
from datetime import date, timedelta

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"


def _call_ollama(system_prompt: str, user_message: str) -> str:
    """Low-level call to Ollama. Returns the response text or an error string."""
    full_prompt = f"System: {system_prompt}\n\nUser: {user_message}\n\nAssistant:"
    payload = {
        "model": MODEL,
        "prompt": full_prompt,
        "stream": False,
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "❌ Cannot connect to Ollama. Make sure it's running with `ollama serve`."
    except requests.exceptions.Timeout:
        return "⏱️ Ollama took too long to respond. Please try again."
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ---------------------------------------------------------------------------
# MEMBER CHATBOT
# ---------------------------------------------------------------------------

def get_member_chat_response(user_message: str, member_name: str, logs_context: list) -> str:
    """
    AI assistant for the Member Dashboard.
    Knows the member's own recent logs and answers productivity/log-related questions.

    logs_context: list of dicts with keys: date, title, description, mood, hours_worked
    """
    today = date.today().strftime("%B %d, %Y")

    if logs_context:
        logs_text = "\n".join([
            f"- [{log.get('date', '')}] {log.get('title', 'No title')} | "
            f"Mood: {log.get('mood', 'N/A')} | "
            f"Hours: {log.get('hours_worked', 'N/A')} | "
            f"Notes: {log.get('description', '')[:120]}"
            for log in logs_context[:10]  # last 10 logs
        ])
    else:
        logs_text = "No logs recorded yet."

    system_prompt = f"""You are a helpful AI assistant for {member_name}, a team member using a daily log tracking app.

Today's date: {today}

{member_name}'s recent work logs:
{logs_text}

Your job:
- Help {member_name} reflect on their work, productivity, and progress.
- Answer questions about their logs (patterns, summaries, what they worked on).
- Suggest improvements to their daily habits or log writing.
- Help them write better log descriptions if asked.
- Keep responses concise, friendly, and practical.
- If asked something unrelated to work/logs, gently redirect to work topics.
- Use their log data to give specific, personalized answers — not generic advice.
"""
    return _call_ollama(system_prompt, user_message)


# ---------------------------------------------------------------------------
# MENTOR CHATBOT
# ---------------------------------------------------------------------------

def get_mentor_chat_response(user_message: str, mentor_name: str, team_context: list) -> str:
    """
    AI assistant for the Mentor Dashboard.
    Knows the full team's recent activity and helps mentors track, analyze, and support their team.

    team_context: list of dicts with keys: member_name, log_date, title, mood, hours_worked, description
    """
    today = date.today().strftime("%B %d, %Y")

    if team_context:
        # Group by member
        members = {}
        for log in team_context:
            name = log.get("member_name", "Unknown")
            if name not in members:
                members[name] = []
            members[name].append(log)

        team_text = ""
        for member_name, logs in members.items():
            team_text += f"\n👤 {member_name}:\n"
            for log in logs[:5]:
                team_text += (
                    f"  • [{log.get('log_date', '')}] {log.get('title', 'No title')} | "
                    f"Mood: {log.get('mood', 'N/A')} | "
                    f"Hours: {log.get('hours_worked', 'N/A')}\n"
                    f"    Notes: {log.get('description', '')[:100]}\n"
                )
    else:
        team_text = "No team logs available yet."

    system_prompt = f"""You are an intelligent AI assistant for {mentor_name}, a team mentor using a daily log tracking system.

Today's date: {today}

Recent team activity:
{team_text}

Your job:
- Help {mentor_name} understand what the team has been working on.
- Identify members who may be struggling (low mood, missing logs, low hours).
- Summarize team progress across different dates or projects.
- Suggest how {mentor_name} can better support specific team members.
- Flag any patterns worth attention (e.g., someone consistently low mood, or not logging).
- Answer questions about any specific member's performance or trends.
- Keep responses professional, insightful, and actionable.
"""
    return _call_ollama(system_prompt, user_message)


# ---------------------------------------------------------------------------
# AI LOG DESCRIPTION HELPER (for Add Log form)
# ---------------------------------------------------------------------------

def suggest_log_description(title: str, mood: str = "", hours: str = "", member_name: str = "") -> dict:
    """
    Generates suggested log content based on the title and context.
    Returns structured suggestions for title, tags, and description.
    """
    context_parts = [f'Log title: "{title}"']
    if mood:
        context_parts.append(f"Mood today: {mood}")
    if hours:
        context_parts.append(f"Hours worked: {hours}")
    if member_name:
        context_parts.append(f"Member: {member_name}")

    context = " | ".join(context_parts)

    system_prompt = """You are a helpful assistant that improves daily work log entries.

Given a log title and optional context, return ONLY valid JSON with the following keys:
- title: an improved, concise log title
- tags: a comma-separated list of 2-4 relevant tags
- description: a clear 2-3 sentence daily log description

Do not return any markdown, explanations, or extra text. Return only JSON.

Example:
{"title": "Improved title here", "tags": "backend, api, testing", "description": "..."}
"""

    user_message = f"Improve this daily log entry: {context}"
    result = _call_ollama(system_prompt, user_message)

    try:
        parsed = json.loads(result)
        return {
            "title": parsed.get("title", title),
            "tags": parsed.get("tags", ""),
            "description": parsed.get("description", result if isinstance(result, str) else ""),
        }
    except Exception:
        return {
            "title": title,
            "tags": "",
            "description": result,
        }


# ---------------------------------------------------------------------------
# AI REPORT (existing — keep this if you already have it)
# ---------------------------------------------------------------------------

def generate_ai_report(logs_data: list, member_name: str, date_range: str) -> str:
    """
    Generates a structured AI summary report for a member's logs over a date range.
    """
    if not logs_data:
        return f"No logs found for {member_name} in the selected date range."

    logs_text = "\n".join([
        f"- [{log.get('date', '')}] {log.get('title', '')} | "
        f"Mood: {log.get('mood', 'N/A')} | Hours: {log.get('hours_worked', 'N/A')} | "
        f"{log.get('description', '')[:150]}"
        for log in logs_data
    ])

    system_prompt = """You are an AI that generates structured performance summaries for team members based on their daily work logs.

Write a professional summary with these sections:
1. **Overview** — brief summary of the work period
2. **Key Accomplishments** — bullet points of what was achieved
3. **Productivity Patterns** — observations about hours, mood, consistency
4. **Areas for Improvement** — constructive suggestions
5. **Recommendation** — one actionable takeaway

Keep the tone professional but encouraging. Be specific — reference actual log content."""

    user_message = f"Generate a report for {member_name} covering {date_range}:\n\n{logs_text}"
    return _call_ollama(system_prompt, user_message)