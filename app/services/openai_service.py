from __future__ import annotations

from openai import OpenAI
from app.core.config import settings


class OpenAIService:
    def __init__(self) -> None:
        # SDK reads key from env automatically too, but we pass explicitly
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def chat(self, system_prompt: str, user_message: str, context_text: str = "", history: list[dict] | None = None) -> str:
        """
        system_prompt: your FinanceAI rules
        context_text: DB snapshot ("USER_CONTEXT ...")
        history: optional list like [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
        """
        messages = [{"role": "system", "content": system_prompt}]

        if context_text:
            # Treat as extra instruction/context. (You can also use role="system")
            messages.append({"role": "user", "content": f"Here is the user's finance data:\n{context_text}"})

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_message})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.4,
        )

        return resp.choices[0].message.content or ""

    def chat_with_context(self, user_message: str, finance_data: dict):

        structured_context = f"""
        Here is the user's financial data:

        Year: {finance_data['year']}
        Month: {finance_data['month']}
        Opening Balance: PKR {finance_data['opening_balance']}
        Monthly Income: PKR {finance_data['monthly_income']}
        Monthly Budget: PKR {finance_data['monthly_budget']}
        Total Expenses: PKR {finance_data['total_expenses']}
        Closing Balance: PKR {finance_data['closing_balance']}
        """

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": structured_context},
            {"role": "user", "content": user_message}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )

        return response.choices[0].message.content