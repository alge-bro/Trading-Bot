# ai_filter.py  (optional — currently not wired into bot.py)
from openai import OpenAI
from config import OPENAI_API_KEY

# openai.ChatCompletion.create(...) was removed in openai>=1.0.
# The current SDK uses a client instance.
client = OpenAI(api_key=OPENAI_API_KEY)


def validate_trade(prompt, model="gpt-4o-mini"):
    """Returns True if the model answers YES. Note: bot.py's commented import
    referenced `ai_filter_approves` — use this name, or alias it there."""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    decision = (resp.choices[0].message.content or "").strip().upper()
    return decision.startswith("YES")