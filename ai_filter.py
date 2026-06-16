# ai_filter.py
import openai
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def validate_trade(prompt: str, model="gpt-4"):
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[{"role":"user", "content":prompt}]
    )
    decision = resp.choices[0].message.content.strip().upper()
    return decision == "YES"
