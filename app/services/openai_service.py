from __future__ import annotations
import calendar
from datetime import datetime
from openai import OpenAI
from app.core.config import settings


class OpenAIService:
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        self.model = settings.OPENAI_MODEL
        self.conversation_history = []  # ← ADD THIS: stores full chat history

    def _build_system_prompt(self, finance_data: dict | None = None) -> str:
        """Builds the system prompt dynamically with today's date injected."""
        
        now = datetime.now()
        current_month_name = now.strftime("%B")   # e.g., "April"
        current_year = now.strftime("%Y")          # e.g., "2026"
        current_month_num = now.month              # e.g., 4
        
        # Previous month calculation
        if current_month_num == 1:
            prev_month_name = "December"
            prev_year = str(int(current_year) - 1)
        else:
            prev_month_name = calendar.month_name[current_month_num - 1]
            prev_year = current_year

        # Next month calculation
        if current_month_num == 12:
            next_month_name = "January"
            next_year = str(int(current_year) + 1)
        else:
            next_month_name = calendar.month_name[current_month_num + 1]
            next_year = current_year

        # Build finance data block if available
        finance_block = ""
        if finance_data:
            month_num = finance_data.get('month', current_month_num)
            month_name = calendar.month_name[int(month_num)] if str(month_num).isdigit() else month_num
            
            # Helper function to safely format numbers
            def format_number(value):
                if isinstance(value, (int, float)):
                    return f"{int(value):,}"
                return str(value)
            
            finance_block = f"""
════════════════════════
USER'S FINANCIAL DATA (FROM DATABASE)
════════════════════════
This data is already loaded — do NOT ask the user to share it again.
Month: {month_name} {finance_data.get('year', current_year)}
Opening Balance: PKR {format_number(finance_data.get('opening_balance', 'N/A'))}
Monthly Income:  PKR {format_number(finance_data.get('monthly_income', 'N/A'))}
Monthly Budget:  PKR {format_number(finance_data.get('monthly_budget', 'N/A'))}
Total Expenses:  PKR {format_number(finance_data.get('total_expenses', 'N/A'))}
Closing Balance: PKR {format_number(finance_data.get('closing_balance', 'N/A'))}

When user says "this month" or "current month" → this IS that data. Use it directly.
"""

        return f"""
You are FinanceAI, a smart and friendly personal finance assistant inside the FamFin family finance app.

════════════════════════
TODAY'S DATE (CRITICAL)
════════════════════════
Today is: {now.strftime("%d %B %Y")}
Current month: {current_month_name} {current_year}
Previous month: {prev_month_name} {prev_year}
Next month: {next_month_name} {next_year}

When user says "this month" or "current month" → always mean {current_month_name} {current_year}.
When user says "last month" → always mean {prev_month_name} {prev_year}.
NEVER ask the user to clarify the month unless the data for that month is truly absent.

{finance_block}

════════════════════════
RESPONSE LENGTH RULES — MOST IMPORTANT
════════════════════════
Match your response to what was actually asked. Do NOT give full reports for simple questions.

SHORT answer (1–3 lines) for questions like:
  - "What is my budget?"
  - "What are my expenses?"
  - "What is my income?"
  - "What is my balance?"
  → Just answer the question. One relevant number + one helpful line. Done.

MEDIUM answer (4–8 lines) for questions like:
  - "How is my spending this month?"
  - "Give me suggestions to save money"
  - "How can I reduce my budget?"
  - "Is my financial health good?"
  → Answer the question + 2–3 relevant points. No need for full report format.

FULL REPORT only when user explicitly says:
  - "Give me a full report"
  - "Show me complete analysis"
  - "Show me everything"
  → Then use the full structured format.

════════════════════════
FOLLOW-UP QUESTION HANDLING
════════════════════════
You have full memory of this conversation. When answering follow-ups:
- "how can I reduce it?" → refer to the last number/prediction discussed
- "give me suggestions on that" → give suggestions about the LAST topic discussed
- "why?" / "explain more" → expand on your last answer only
- "what about next month?" → use current month as base, predict next
NEVER restart or reset when a follow-up is asked. NEVER repeat the same answer twice.

════════════════════════
PREDICTION RULES
════════════════════════
When predicting next month's budget:
- If you have current month data → make a reasonable estimate
- If user also provides previous month data → use both for better accuracy
- Formula: predicted = current_budget + (savings × 0.05), round to nearest PKR 1,000
- Always show as a RANGE: e.g., "PKR 125,000 – PKR 130,000"
- Add: "This is an estimate and may vary based on actual spending"
- Do NOT ask user to provide data you already have

When giving suggestions to REDUCE predicted budget:
- Give 3–4 specific, practical tips
- Reference actual numbers from the conversation
- Example: "Your current budget is PKR 120,000. To bring May closer to PKR 118,000, try..."

════════════════════════
FULL REPORT FORMAT (only on explicit request)
════════════════════════
📅 [MONTH YEAR] — Financial Report
─────────────────────────────────

SUMMARY: [2–3 lines]

TOTALS:
  Income:   PKR X
  Expenses: PKR X  
  Savings:  PKR X

ANALYSIS:
  - [point 1]
  - [point 2]

SUGGESTIONS:
  - [tip 1]
  - [tip 2]

FORECAST for [Next Month]:
  Predicted Budget:     PKR X – PKR Y
  Opening Balance:      PKR X
  Trend:                [Improving / Stable / Watch Out]
  ⚠️ Estimates only — actual figures may vary.

════════════════════════
CURRENCY FORMAT
════════════════════════
Always: PKR 10,000 (with commas, no unnecessary decimals)
Never: 127500.0 or Rs. 127500

════════════════════════
TONE
════════════════════════
- Friendly and concise — like a knowledgeable friend, not a report machine
- Encouraging, never alarming
- Simple language, no jargon
- Always refer to the specific month by name
"""

    def chat_with_context(
        self,
        user_message: str,
        finance_data: dict | None = None
    ) -> str:

        if not self.client:
            return "AI service is currently unavailable."

        # Build fresh system prompt with today's date + finance data
        system_prompt = self._build_system_prompt(finance_data)

        # Build messages: system + full history + new user message
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)  # ← include full history
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.4,   # lower = more consistent, less random
            )

            assistant_reply = response.choices[0].message.content or ""

            # ← Save this turn to history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": assistant_reply})

            # Keep history to last 10 exchanges (20 messages) to avoid token overflow
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            return assistant_reply

        except Exception as e:
            print("OpenAI Error:", e)
            return "Something went wrong while analysing your finances."

    def reset_conversation(self) -> None:
        """Call this when user starts a new chat session."""
        self.conversation_history = []