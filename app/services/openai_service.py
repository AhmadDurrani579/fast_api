from __future__ import annotations

from openai import OpenAI
from app.core.config import settings


class OpenAIService:
    def __init__(self) -> None:
        # SDK reads key from env automatically too, but we pass explicitly
        if not settings.OPENAI_API_KEY:
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        self.system_prompt = """
            You are FinanceAI, a smart and friendly personal finance assistant.

            ––––––––––––––––––––
            CORE RULES
            ––––––––––––––––––––
            - Always be clear, structured, and easy to understand.
            - Never give confusing or long explanations.
            - Always format responses cleanly.

            ––––––––––––––––––––
            DATA HANDLING
            ––––––––––––––––––––
            - If financial data is provided → analyse it.
            - If no financial data → respond conversationally and ask what user needs.
            - Never say "No data found".

            ––––––––––––––––––––
            CURRENCY
            ––––––––––––––––––––
            All values must be in PKR format:
            Example: PKR 10,000

            ––––––––––––––––––––
            FINANCIAL ANALYSIS
            ––––––––––––––––––––
            When data is provided:

            1. Calculate:
            savings = monthly_income − total_expenses

            2. Determine:
            - Healthy spending (if savings > 20% income)
            - Average (10–20%)
            - Poor (<10%)

            3. Predict next month:
            predicted_budget = monthly_budget + (5% of savings)
            next_opening_balance = closing_balance

            ––––––––––––––––––––
            STRICT OUTPUT FORMAT (VERY IMPORTANT)
            ––––––––––––––––––––

            Respond ONLY in this structure:

            SUMMARY:
            - 2–3 lines maximum explaining financial situation

            TOTALS:
            Income: PKR X
            Expenses: PKR X
            Savings: PKR X

            ANALYSIS:
            - 2–3 bullet points about spending behaviour

            SUGGESTIONS:
            - 2–3 actionable improvements

            FORECAST:
            {
            "predicted_budget": "PKR X",
            "next_opening_balance": "PKR X"
            }

            ––––––––––––––––––––
            IF NO DATA
            ––––––––––––––––––––
            Reply normally and ask:
            "How can I help you with your finances today?"

            ––––––––––––––––––––
            TONE
            ––––––––––––––––––––
            Friendly, confident, and professional.
            """        
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

    def chat_with_context(
        self,
        user_message: str,
        finance_data: dict | None = None
    ) -> str:

        # 🚨 Safety check
        if not self.client:
            return "AI service is currently unavailable."

        messages = [
            {"role": "system", "content": self.system_prompt}
        ]

        # ---------------------------------
        # Inject finance data safely
        # ---------------------------------
        if finance_data:
            finance_summary = f"""
                Financial Data:
                Year: {finance_data.get('year')}
                Month: {finance_data.get('month')}
                Opening Balance: {finance_data.get('opening_balance')}
                Monthly Income: {finance_data.get('monthly_income')}
                Monthly Budget: {finance_data.get('monthly_budget')}
                Closing Balance: {finance_data.get('closing_balance')}
                Total Expenses: {finance_data.get('total_expenses')}
                """
            messages.append({
                "role": "system",
                "content": finance_summary
            })

        # ---------------------------------
        # Append user message
        # ---------------------------------
        messages.append({
            "role": "user",
            "content": user_message
        })

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.6,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            print("OpenAI Error:", e)
            return "Something went wrong while analysing your finances."