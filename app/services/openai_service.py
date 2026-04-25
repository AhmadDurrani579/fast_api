from __future__ import annotations
import calendar
from openai import OpenAI
from app.core.config import settings


class OpenAIService:

    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = settings.OPENAI_MODEL

        # ─── Base identity prompt (always injected) ───
        self.base_system_prompt = """
You are FinanceAI, a smart, friendly, and professional personal finance assistant
for a family budgeting application.

CORE RULES:
- Always be clear, structured, and concise.
- All currency values must be in PKR format: e.g. PKR 10,000
- Always reference the specific month and year by name in every response (e.g. "April 2026").
- Never mix data from different months in the same analysis.
- Never make up numbers — only use the data provided to you.
- Be encouraging, not alarming, even when finances look poor.
- Keep responses clean and well-formatted using simple text, not HTML.
- Use emojis sparingly but warmly.
"""

    # ─────────────────────────────────────────────
    # INTENT-SPECIFIC SYSTEM PROMPTS
    # ─────────────────────────────────────────────

    def _budget_lookup_prompt(self) -> str:
        return """
TASK: Budget Lookup for a specific month.

The user is asking about their budget and financial summary for a given month.
You will be given:
- Opening balance, monthly income, monthly budget, closing balance
- Total expenses for the month
- A category_breakdown list showing per-category budget vs actual spending

Your response MUST follow this exact format:

📅 [MONTH YEAR] — Financial Summary
─────────────────────────────────────

OVERVIEW:
Income:           PKR X
Budget Set:       PKR X
Total Spent:      PKR X
Remaining Budget: PKR X
Savings:          PKR X
Opening Balance:  PKR X
Closing Balance:  PKR X

CATEGORY BREAKDOWN:
For each category show: Category | Budgeted | Spent | Remaining | Status
Status = ✅ On Track / ⚠️ Near Limit (>80% used) / 🔴 Over Budget

FINANCIAL HEALTH: [Healthy / Average / Needs Attention]
- Healthy  → savings > 20% of income
- Average  → savings 10–20% of income
- Needs Attention → savings < 10% of income

QUICK INSIGHT:
- 2–3 bullet points about spending behaviour this month.
"""

    def _prediction_prompt(self) -> str:
        return """
TASK: Budget Prediction for a future month.

The user wants a predicted budget for an upcoming month.
You will be given:
- Current month's income, budget, expenses, savings, closing balance
- Up to 3 previous months of data for trend analysis
- Current category budgets and expenses

Your response MUST follow this exact format:

🔮 BUDGET FORECAST — [TARGET MONTH YEAR]
─────────────────────────────────────

BASED ON: [list the months used for this prediction]

PREDICTED FIGURES:
Estimated Income:          PKR X (based on [current/avg] income)
Predicted Budget:          PKR X,XXX – PKR X,XXX  ← always show as a range
Predicted Opening Balance: PKR X  (= current closing balance)
Estimated Savings:         PKR X – PKR X

PREDICTION METHOD:
- Show how many months of data were used
- If 3 months: use rolling average of savings to adjust budget
- If 2 months: use simple trend
- If 1 month: use conservative estimate with ±5% range
- Round all figures to nearest PKR 500

CATEGORY PREDICTIONS:
For each budgeted category, suggest a predicted budget for next month
based on spending patterns. Flag any categories trending upward.

TREND: [Improving 📈 / Stable ➡️ / Needs Attention 📉]

⚠️ Note: These are estimates based on historical data. Actual figures may vary.
"""

    def _spending_control_prompt(self) -> str:
        return """
TASK: Spending Control Analysis & Advice.

The user wants to understand where they are overspending and how to improve.
You will be given:
- Monthly income, budget, total expenses
- A detailed category_breakdown showing per-category budget vs actual spending
  including: category name, budgeted amount, spent amount, % used, whether overspent

Your response MUST follow this exact format:

💡 SPENDING ANALYSIS — [MONTH YEAR]
─────────────────────────────────────

OVERALL STATUS:
Total Budget:  PKR X
Total Spent:   PKR X
Difference:    PKR X (Over/Under budget)

🔴 OVERSPENT CATEGORIES:
For each overspent category:
• [Category]: Budgeted PKR X → Spent PKR X (X% over)
  → Tip: [1 specific, actionable tip for this category]

⚠️ NEAR LIMIT CATEGORIES (80–100% used):
• [Category]: PKR X remaining

✅ WELL-MANAGED CATEGORIES:
• List categories under 70% of budget — brief praise

TOP 3 RECOMMENDATIONS:
1. [Most impactful change to make]
2. [Second most impactful]
3. [Third most impactful]

SAVINGS OPPORTUNITY:
If you reduce spending in [top 2 overspent cats] by [X%],
you could save an extra PKR X per month.

Keep advice specific, friendly, and actionable. Avoid generic advice like "spend less".
"""

    def _general_finance_prompt(self) -> str:
        return """
TASK: General finance conversation.

The user is asking a general finance question not tied to specific month data.
Respond helpfully and conversationally. If the question is about budgeting strategy,
savings tips, or financial planning, give practical advice.

Keep the response concise — 3–5 sentences or a short bullet list.
Always offer to look up their specific data if relevant.
"""

    # ─────────────────────────────────────────────
    # FINANCE DATA FORMATTER
    # ─────────────────────────────────────────────

    def _format_finance_context(self, finance_data: dict) -> str:
        """
        Converts the finance_data dict into a structured text block
        injected as a system message so the model has clean data to work with.
        """
        intent = finance_data.get("intent", "budget_lookup")
        month_num = finance_data.get("month") or finance_data.get("current_month")
        year = finance_data.get("year") or finance_data.get("current_year")
        month_name = calendar.month_name[month_num] if month_num else "Unknown"

        lines = [
            "═══ FINANCIAL DATA ═══",
            f"Month: {month_name} {year}",
            f"Intent: {intent}",
            "",
        ]

        # Core financials
        for key, label in [
            ("opening_balance", "Opening Balance"),
            ("monthly_income", "Monthly Income"),
            ("monthly_budget", "Monthly Budget"),
            ("closing_balance", "Closing Balance"),
            ("total_expenses", "Total Expenses"),
            ("remaining_budget", "Remaining Budget"),
            ("savings", "Savings"),
            ("current_savings", "Current Savings"),
        ]:
            if finance_data.get(key) is not None:
                lines.append(f"{label}: PKR {finance_data[key]:,.0f}")

        # Category breakdown (budget_lookup / spending_control)
        cat_breakdown = finance_data.get("category_breakdown", [])
        if cat_breakdown:
            lines.append("")
            lines.append("─── CATEGORY BREAKDOWN ───")
            for cat in cat_breakdown:
                status = "🔴 OVER BUDGET" if cat.get("overspent") else (
                    "⚠️ NEAR LIMIT" if cat.get("percent_used", 0) >= 80 else "✅ OK"
                )
                lines.append(
                    f"  {cat['category']} [{cat.get('scope','family')}]: "
                    f"Budget PKR {cat['budget']:,.0f} | "
                    f"Spent PKR {cat['spent']:,.0f} | "
                    f"Remaining PKR {cat['remaining']:,.0f} | "
                    f"{cat.get('percent_used', 0)}% used | {status}"
                )

        # Prediction-specific data
        if intent == "prediction":
            target_month = finance_data.get("target_month")
            target_year = finance_data.get("target_year")
            if target_month and target_year:
                lines.append("")
                lines.append(f"Target Prediction Month: {calendar.month_name[target_month]} {target_year}")
                lines.append(f"Months Ahead: {finance_data.get('months_ahead', 1)}")

            prev_months = finance_data.get("previous_months", [])
            if prev_months:
                lines.append("")
                lines.append("─── HISTORICAL DATA ───")
                for pm in prev_months:
                    pm_name = calendar.month_name[pm["month"]]
                    lines.append(
                        f"  {pm_name} {pm['year']}: "
                        f"Income PKR {pm['monthly_income']:,.0f} | "
                        f"Budget PKR {pm['monthly_budget']:,.0f} | "
                        f"Closing Balance PKR {pm['closing_balance']:,.0f}"
                    )
            else:
                lines.append("")
                lines.append("Historical Data: Only current month available (1 month of data)")

            # Category budgets & expenses for prediction
            cat_budgets = finance_data.get("category_budgets", [])
            cat_expenses = finance_data.get("category_expenses", {})
            if cat_budgets:
                lines.append("")
                lines.append("─── CURRENT CATEGORY SPENDING ───")
                for cb in cat_budgets:
                    spent = cat_expenses.get(cb["category"], 0)
                    lines.append(
                        f"  {cb['category']}: Budget PKR {cb['budget']:,.0f} | "
                        f"Spent PKR {spent:,.0f}"
                    )

        lines.append("═══════════════════════")
        return "\n".join(lines)

    # ─────────────────────────────────────────────
    # MAIN CHAT METHOD
    # ─────────────────────────────────────────────

    def chat_with_context(
        self,
        user_message: str,
        finance_data: dict | None = None
    ) -> str:

        if not self.client:
            return "AI service is currently unavailable. Please check your API configuration."

        intent = finance_data.get("intent") if finance_data else "general"

        # Pick the right task-specific prompt
        intent_prompt_map = {
            "budget_lookup":    self._budget_lookup_prompt(),
            "prediction":       self._prediction_prompt(),
            "spending_control": self._spending_control_prompt(),
            "general":          self._general_finance_prompt(),
        }
        task_prompt = intent_prompt_map.get(intent, self._general_finance_prompt())

        # Build messages
        messages = [
            {"role": "system", "content": self.base_system_prompt},
            {"role": "system", "content": task_prompt},
        ]

        # Inject structured finance data if available
        if finance_data:
            formatted = self._format_finance_context(finance_data)
            messages.append({
                "role": "system",
                "content": f"Here is the user's financial data for this request:\n\n{formatted}"
            })

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,   # Lower = more consistent, factual responses
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            print(f"[OpenAI Error] {e}")
            return "Something went wrong while analysing your finances. Please try again."

    # ─────────────────────────────────────────────
    # LEGACY METHOD (kept for compatibility)
    # ─────────────────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        context_text: str = "",
        history: list[dict] | None = None
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        if context_text:
            messages.append({"role": "user", "content": f"Finance data:\n{context_text}"})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.4,
        )
        return resp.choices[0].message.content or ""