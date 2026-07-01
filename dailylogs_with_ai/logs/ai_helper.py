"""
ai_helper.py
─────────────────────────────────────────────────────────────
Helper functions that talk to the OpenAI API to generate a
"weekly / range" summary report from a member's daily logs.

Requires:
    pip install openai

Set OPENAI_API_KEY as an environment variable (see settings.py).
"""

from openai import OpenAI
from django.conf import settings

_client = None


def _get_client():
    """Lazily create the OpenAI client (avoids crashing on import if key missing)."""
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your environment variables."
            )
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _logs_to_text(logs):
    """Convert a queryset/list of Log objects into a readable block of text."""
    if not logs:
        return "No logs were recorded in this date range."

    lines = []
    for l in logs:
        lines.append(
            f"- {l.date} | {l.title} "
            f"({l.hours_spent}h) "
            f"Tags: {l.tags or 'none'} "
            f"Description: {l.description or '(no description)'}"
        )
    return "\n".join(lines)


def build_report_prompt(logs, missing_dates, missing_reasons, start_date, end_date, feedback=None):
    """
    Construct the prompt sent to the AI.

    logs            : list of Log objects within [start_date, end_date]
    missing_dates   : list of date objects with no log entry
    missing_reasons : dict {date_str: reason_text} supplied by the member
    feedback        : optional string — member's request for regeneration
    """
    logs_text = _logs_to_text(logs)

    missing_text = "None — every day in the range has a log entry."
    if missing_dates:
        rows = []
        for d in missing_dates:
            ds = str(d)
            reason = missing_reasons.get(ds, "").strip()
            reason = reason if reason else "(no reason given)"
            rows.append(f"- {ds}: {reason}")
        missing_text = "\n".join(rows)

    prompt = f"""You are an assistant that writes a clear, professional progress
summary report for a daily-log tracking app, covering {start_date} to {end_date}.

DAILY LOG ENTRIES:
{logs_text}

DAYS WITH NO LOG ENTRY (and the member's stated reason, if any):
{missing_text}

Write a summary report with these sections:
1. Overview — 2-3 sentences on overall progress and total hours worked.
2. Key Activities — bullet points of the main tasks/work done, grouped logically.
3. Gaps / Missing Days — briefly mention any days with no entry and the reason given (if any). If no days are missing, say so.
4. Suggestions — 1-2 short, constructive suggestions for the upcoming period.

Keep it concise, professional, and easy for a mentor to skim."""

    if feedback:
        prompt += f"""

NOTE: A previous version of this report was generated. The user was not fully
satisfied and gave this feedback for regenerating the report:
"{feedback}"

Please regenerate the report taking this feedback into account."""

    return prompt


def generate_report(logs, missing_dates, missing_reasons, start_date, end_date, feedback=None):
    """
    Call the OpenAI Chat Completions API and return the generated report text.
    """
    client = _get_client()
    prompt = build_report_prompt(logs, missing_dates, missing_reasons, start_date, end_date, feedback)

    response = client.chat.completions.create(
        model="gpt-4o-mini",   # cheap + good enough for summaries; change if you like
        messages=[
            {"role": "system", "content": "You are a helpful assistant that writes concise work progress reports."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=600,
    )

    return response.choices[0].message.content.strip()
