from openai import OpenAI
from app.core.config import settings
from datetime import datetime
import json

client = OpenAI(api_key=settings.OPENAI_API_KEY)

MODEL = "gpt-4.1-mini"


SYSTEM_PROMPT = """
Extract the month and year from the user's message.

Rules:
- If user mentions a specific month and year, return that.
- If user says "last month", calculate properly.
- If user says nothing about month/year, return current month and year.
- Return ONLY valid JSON.

Format:
{
  "year": 2025,
  "month": 12
}
"""


def extract_month_year(user_message: str):
    now = datetime.utcnow()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(content)
        return parsed
    except:
        # fallback to current month if parsing fails
        return {
            "year": now.year,
            "month": now.month
        }