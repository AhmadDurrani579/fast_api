import json
from datetime import datetime
from openai import OpenAI
from app.core.config import settings


SYSTEM_PROMPT = """
Extract the month and year from the user message.
Return strictly in JSON format:
{
  "year": 2025,
  "month": 12
}
If no date is found, return current month and year.
"""


class DateExtractor:

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def extract_month_year(self, user_message: str):
        now = datetime.utcnow()

        if not self.client:
            return {
                "year": now.year,
                "month": now.month
            }

        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0
            )

            content = response.choices[0].message.content.strip()

            parsed = json.loads(content)
            return parsed

        except Exception:
            return {
                "year": now.year,
                "month": now.month
            }