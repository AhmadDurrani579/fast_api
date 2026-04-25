from __future__ import annotations
import calendar
from openai import OpenAI
from app.core.config import settings


class OpenAIService:

    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model  = settings.OPENAI_MODEL

        # ─── Base identity & tone (always injected first) ───
        self.base_system_prompt = """
You are FinanceAI — a smart, friendly personal finance assistant built into a family budgeting app.
You're like a knowledgeable friend who understands money — warm, direct, and easy to talk to.

━━━ TONE — THIS IS YOUR MOST IMPORTANT RULE ━━━

Talk like a helpful human friend, NOT like a bank statement or a corporate report.

✅ GOOD tone examples:
  "So in February, your income was PKR 150,000 and you budgeted PKR 120,000.
   You spent PKR 114,900 in total — which means you were actually under budget
   by PKR 5,100. Not bad at all! 💪"

  "Groceries went a bit over — PKR 27,500 against a PKR 25,000 budget.
   Happens to everyone, honestly. The bigger issue is Dining Out, which
   was PKR 3,200 over. That's the one worth watching."

❌ BAD tone examples (never do this):
  "OVERVIEW: Income: PKR 150,000 | Budget Set: PKR 120,000"
  "📅 February 2026 — Financial Summary ─────────"
  "FINANCIAL HEALTH: Needs Attention"
  Pipe-separated tables, rigid headers, robotic labels

━━━ FORMATTING RULES ━━━
- NO big headers, NO report-style titles, NO pipe tables
- Open naturally: "So for February..." or "Looking at March..." or "Here's the thing..."
- Use short paragraphs — 2-3 sentences max per paragraph
- Bullet points only when listing 3+ categories — keep them short
- Mobile users are reading this on a small screen — keep it tight
- Use 1-2 emojis max per response — only where they genuinely add warmth
- Never write walls of text

━━━ DATA RULES ━━━
- Never make up numbers — only use data provided to you
- Always mention the month by name (e.g. "February 2026")
- Never mix data from different months in the same response
- All amounts in PKR: PKR 10,000 / PKR 1,50,000

━━━ IF NO DATA PROVIDED ━━━
Reply warmly and ask what they need:
"Hey! I'm here to help with your family finances 😊
Ask me about your budget for any month, get a prediction
for next month, or ask how to cut down on spending."
"""

    # ─────────────────────────────────────────────
    # INTENT PROMPTS — conversational style
    # ─────────────────────────────────────────────

    def _budget_lookup_prompt(self) -> str:
        return """
TASK: The user is asking about their budget for a specific month.

You have their full financial data for that month including category-level breakdown.

HOW TO RESPOND:
1. Open with a natural 1-2 sentence summary of how the month looks overall.
   e.g. "So in February 2026, you brought in PKR 150,000 and set yourself
   a budget of PKR 120,000. Overall you spent PKR 114,900 — decent control!"

2. Give the key numbers in plain sentences (NOT a table):
   Income, budget set, total spent, remaining budget, savings.

3. Talk through the categories conversationally:
   - Lead with the overspent ones — mention the specific overage amount
   - Then briefly note the well-managed ones
   - Keep it short — don't list every category robotically

4. End with 1-2 sentences on financial health — warm and encouraging even if bad.

RULES:
- Do NOT use headers like "OVERVIEW:" or "CATEGORY BREAKDOWN:"
- Do NOT use pipe tables
- Keep the whole response under 200 words
- Sound like a friend giving a quick money check-in, not a bank report
"""

    def _prediction_prompt(self) -> str:
        return """
TASK: The user wants a budget prediction for a future month.

You have current month data, up to 3 previous months of history,
and current category spending patterns.

HOW TO RESPOND:
1. Open by acknowledging what data you're basing this on.
   e.g. "Based on your last 2 months, here's what I'd expect for May 2026..."
   or "Looking at your March numbers, here's a rough forecast for April..."

2. Give the prediction conversationally:
   - Estimated income (usually same as current unless trend shows change)
   - Predicted budget range — always a range, e.g. PKR 118,000 – PKR 122,000
   - Expected opening balance (= current closing balance)
   - Rough savings estimate

3. Call out 1-2 categories that look like they might cause problems next month
   based on recent trends — specific and practical.

4. Close with a brief encouraging note about what to watch.

RULES:
- Always show budget as a RANGE (±5%) — never a single exact figure
- Always add one line: "This is an estimate — actual figures will vary."
- Do NOT use rigid headers or tables
- Keep under 180 words
- More months of data = more confident tone. Less data = more cautious tone.
  If only 1 month available, say "Based on just one month of data, this is
  a rough estimate — I'll get more accurate as we have more history."
"""

    def _spending_control_prompt(self) -> str:
        return """
TASK: The user wants advice on controlling their spending.

You have their full category breakdown showing what was budgeted vs actually spent.

HOW TO RESPOND:
1. Start with a quick, honest overall picture — 1-2 sentences.
   e.g. "Honestly, this month wasn't too bad overall — but there are
   2-3 categories that are quietly eating into your budget."

2. Call out the overspent categories specifically:
   - Name the category, say how much over, give ONE specific actionable tip
   - Be conversational: "Dining Out was PKR 3,200 over budget — eating out
     twice a week adds up fast. Even cutting one meal out a week could
     save you around PKR 1,600 a month."

3. Briefly praise the well-managed categories — 1 sentence max.

4. End with a concrete savings opportunity:
   e.g. "If you trim Dining Out and Entertainment by around 20%,
   you could free up roughly PKR 4,000 extra every month."

RULES:
- Be specific — use the actual numbers from the data
- No generic advice like "spend less" or "create a budget"
- No headers, no tables, no pipe characters
- Warm and encouraging tone — never make them feel bad
- Keep under 220 words
- The goal is 2-3 actionable insights, not an exhaustive list
"""

    def _general_finance_prompt(self) -> str:
        return """
TASK: General finance question — no specific month data provided.

Respond helpfully and conversationally, like a knowledgeable friend.
If it's a budgeting or savings question, give practical real-world advice.
Keep it to 3-5 sentences or a short bullet list.
Offer to look up their specific data if relevant.
Never be preachy or overly formal.
"""

    # ─────────────────────────────────────────────
    # FINANCE DATA FORMATTER
    # ─────────────────────────────────────────────

    def _format_finance_context(self, finance_data: dict) -> str:
        """
        Converts finance_data into a clean labelled text block
        injected as a system message. The model reads this as raw data
        and uses it to generate a conversational response.
        """
        intent   = finance_data.get("intent", "budget_lookup")
        month_n  = finance_data.get("month") or finance_data.get("current_month")
        year     = finance_data.get("year")  or finance_data.get("current_year")
        month_name = calendar.month_name[month_n] if month_n else "Unknown"

        lines = [
            "━━━ USER FINANCIAL DATA ━━━",
            f"Month: {month_name} {year}",
            f"Intent: {intent}",
            "",
        ]

        # Core financials
        field_labels = [
            ("opening_balance",  "Opening Balance"),
            ("monthly_income",   "Monthly Income"),
            ("monthly_budget",   "Monthly Budget"),
            ("closing_balance",  "Closing Balance"),
            ("total_expenses",   "Total Expenses"),
            ("remaining_budget", "Remaining Budget"),
            ("savings",          "Savings"),
            ("current_savings",  "Current Savings"),
        ]
        for key, label in field_labels:
            val = finance_data.get(key)
            if val is not None:
                lines.append(f"{label}: PKR {val:,.0f}")

        # Category breakdown
        cat_breakdown = finance_data.get("category_breakdown", [])
        if cat_breakdown:
            lines.append("")
            lines.append("── Category Breakdown ──")
            for cat in cat_breakdown:
                if cat.get("overspent"):
                    status = "OVER BUDGET"
                elif cat.get("percent_used", 0) >= 80:
                    status = "NEAR LIMIT"
                else:
                    status = "OK"

                lines.append(
                    f"  {cat['category']} ({cat.get('scope','family')}): "
                    f"Budget PKR {cat['budget']:,.0f} | "
                    f"Spent PKR {cat['spent']:,.0f} | "
                    f"Remaining PKR {cat['remaining']:,.0f} | "
                    f"{cat.get('percent_used', 0)}% used | {status}"
                )

        # Prediction-specific fields
        if intent == "prediction":
            target_month = finance_data.get("target_month")
            target_year  = finance_data.get("target_year")
            if target_month and target_year:
                lines.append("")
                lines.append(f"Predicting For: {calendar.month_name[target_month]} {target_year}")
                lines.append(f"Months Ahead: {finance_data.get('months_ahead', 1)}")

            prev_months = finance_data.get("previous_months", [])
            if prev_months:
                lines.append("")
                lines.append("── Historical Data ──")
                for pm in prev_months:
                    lines.append(
                        f"  {calendar.month_name[pm['month']]} {pm['year']}: "
                        f"Income PKR {pm['monthly_income']:,.0f} | "
                        f"Budget PKR {pm['monthly_budget']:,.0f} | "
                        f"Closing Balance PKR {pm['closing_balance']:,.0f}"
                    )
            else:
                lines.append("")
                lines.append("Historical Data: Only current month available — use cautious estimate.")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
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

        # Pick the right task prompt
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

        # Inject structured finance data
        if finance_data:
            formatted = self._format_finance_context(finance_data)
            messages.append({
                "role": "system",
                "content": f"Here is the user's financial data — use this to respond:\n\n{formatted}"
            })

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.5,
                max_tokens=600,
            )
            return response.choices[0].message.content or ""

        except Exception as e:
            print(f"[OpenAI Error] {e}")
            return "Something went wrong while checking your finances. Please try again in a moment."

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
            temperature=0.5,
        )
        return resp.choices[0].message.content or ""