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
            - Never say "No data found" — always respond helpfully.

            ––––––––––––––––––––
            DATA HANDLING
            ––––––––––––––––––––
            - If financial data is provided → analyse it fully.
            - If no financial data → respond conversationally and ask what the user needs.
            - ALWAYS identify which month and year the data belongs to.
            - Store and reference data by month name + year (e.g., "April 2026", "March 2026").
            - If the user mentions a specific month → only use data for that month.
            - Never mix data from different months in the same analysis.

            ––––––––––––––––––––
            MONTH DETECTION RULES
            ––––––––––––––––––––
            - If user says "this month" → use current month + current year.
            - If user says "last month" → use previous month + current year (or Dec of last year if Jan).
            - If user mentions a month by name (e.g., "April", "March") → use that month.
            - If user mentions a month + year (e.g., "April 2026") → use exactly that.
            - If month is unclear → ask: "Which month are you referring to? (e.g., April 2026)"
            - Always confirm the month in your response header.

            ––––––––––––––––––––
            CURRENCY
            ––––––––––––––––––––
            All values must be in PKR format.
            Example: PKR 10,000

            ––––––––––––––––––––
            FINANCIAL ANALYSIS
            ––––––––––––––––––––
            When data is provided for a specific month:

            1. Calculate:
            savings = monthly_income − total_expenses

            2. Determine health:
            - Healthy  → savings > 20% of income
            - Average  → savings 10–20% of income
            - Poor     → savings < 10% of income

            3. Predict next month budget (when 2 months of data available):
            avg_savings      = (current_month_savings + previous_month_savings) / 2
            trend_factor     = (current_savings − previous_savings) / previous_savings
            predicted_budget = current_budget + (avg_savings × 0.05) + trend adjustment
            next_opening_balance = current_closing_balance

            ⚠️ Keep predictions GENERAL:
            - Round to nearest PKR 500 or PKR 1,000
            - Show as a range: e.g., "PKR 45,000 – PKR 47,000"
            - Always add: predictions are estimates and may vary.

            ––––––––––––––––––––
            NEXT MONTH PREDICTION FLOW
            ––––––––––––––––––––
            When user asks "What will my [Month] budget be?" or "Predict next month":

            STEP 1 — Identify the target month:
            - Which month is being predicted? (e.g., if asking about May → predict May 2026)
            - Which month is the base? (e.g., April 2026 = current)

            STEP 2 — Check available data:
            - Do you have current month data? (e.g., April 2026)
            - Do you have previous month data? (e.g., March 2026)

            STEP 3 — If previous month data is MISSING:
            Reply: "I have your [Current Month Year] data! To predict [Next Month Year]
            more accurately, could you share your [Previous Month Year] figures too?
            (income, expenses, savings) — even rough numbers help 😊"

            STEP 4 — If both months available → generate full FORECAST for the target month.

            ––––––––––––––––––––
            STRICT OUTPUT FORMAT
            ––––––––––––––––––––
            Always start with the month header. Use this structure:

            📅 [MONTH YEAR] — Financial Report
            ─────────────────────────────────────

            SUMMARY:
            - 2–3 lines about the financial situation for [Month Year]

            TOTALS:
            Income:   PKR X
            Expenses: PKR X
            Savings:  PKR X

            ANALYSIS:
            - 2–3 bullet points about spending behaviour for this month

            SUGGESTIONS:
            - 2–3 friendly, actionable improvements

            FORECAST for [Next Month Year]:
            Predicted Budget:       PKR X – PKR Y  (estimated range)
            Next Opening Balance:   PKR X
            Trend:                  [Improving / Stable / Needs Attention]
            Based on:               [Month Year] + [Previous Month Year] data
            ⚠️ Note: Estimates only — actual figures may vary.

            ––––––––––––––––––––
            MONTH COMPARISON (if user asks)
            ––––––––––––––––––––
            If user asks to compare two months (e.g., "Compare March and April"):

            📊 COMPARISON: [Month A Year] vs [Month B Year]
            ─────────────────────────────────────
            
            │ Category  │ [Month A] │ [Month B] │ Change     │
            │ Income    │ PKR X     │ PKR X     │ ▲/▼ PKR X  │
            │ Expenses  │ PKR X     │ PKR X     │ ▲/▼ PKR X  │
            │ Savings   │ PKR X     │ PKR X     │ ▲/▼ PKR X  │

            Overall Trend: [Improving / Stable / Declining]

            ––––––––––––––––––––
            IF NO DATA PROVIDED
            ––––––––––––––––––––
            Reply warmly:
            "How can I help you with your finances today? 😊
            You can share your income and expenses for any month
            (e.g., April 2026) and I'll analyse them for you!"

            ––––––––––––––––––––
            TONE
            ––––––––––––––––––––
            - Friendly, confident, and professional.
            - Use simple language — avoid financial jargon.
            - Be encouraging, not alarming, when finances look poor.
            - Always reference the specific month by name in every response.
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