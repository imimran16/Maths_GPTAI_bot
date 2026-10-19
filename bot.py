
import os
import logging
from collections import defaultdict, deque

from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

chats = defaultdict(lambda: deque(maxlen=12))

INSTRUCTIONS = """
You are MathsGPT, an expert mathematics tutor.
Help students with Class 11 and 12 mathematics,
NCERT and UP Board topics.
Explain solutions step by step in simple Hindi
when the student writes in Hindi or Hinglish.
Show formulas, calculations and the final answer.
If a question is unclear, ask for clarification.
Never invent a mathematical result.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📐 Welcome to MathsGPT!\n\n"
        "Main Maths ke sawal step-by-step solve karta hoon.\n"
        "Apna sawal bhejo.\n\n"
        "/reset - Chat history clear karein"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats.pop(update.effective_user.id, None)
    await update.message.reply_text("Chat reset ho gayi! ✅")

async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    question = update.message.text.strip()

    if len(question) > 4000:
        await update.message.reply_text("Kripya chhota sawal bhejein.")
        return

    status = await update.message.reply_text("🧮 Sawal solve ho raha hai...")

    try:
        response = await client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input=list(chats[uid]) + [
                {"role": "user", "content": question}
            ],
            max_output_tokens=1000,
        )

        answer = response.output_text or "Jawab nahi mil saka."
        chats[uid].append({"role": "user", "content": question})
        chats[uid].append({"role": "assistant", "content": answer})

        chunks = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
        await status.edit_text(chunks[0])

        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)

    except Exception:
        logging.exception("MathsGPT request failed")
        await status.edit_text(
            "⚠️ Abhi jawab nahi mil saka. "
            "API key, billing aur model settings check karein."
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, solve))
    app.run_polling()

if __name__ == "__main__":
    main()
