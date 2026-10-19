import os
import asyncio
import logging
from collections import defaultdict, deque

from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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


async def generate_answer(history):
    for attempt in range(3):
        try:
            return await client.aio.models.generate_content(
                model=MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=INSTRUCTIONS,
                    max_output_tokens=1000,
                ),
            )

        except Exception as e:
            error = str(e)
            logging.exception(
                "Gemini request failed (attempt %s/3)",
                attempt + 1,
            )

            temporary = any(
                code in error.upper()
                for code in (
                    "503",
                    "UNAVAILABLE",
                    "429",
                    "RESOURCE_EXHAUSTED",
                    "500",
                    "502",
                    "504",
                    "INTERNAL",
                    "TIMEOUT",
                )
            )

            if not temporary or attempt == 2:
                raise

            await asyncio.sleep(2 ** (attempt + 1))

    raise RuntimeError("Gemini request failed after retries")


async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    question = update.message.text.strip()

    if len(question) > 4000:
        await update.message.reply_text("Kripya chhota sawal bhejein.")
        return

    status = await update.message.reply_text(
        "🧮 Sawal solve ho raha hai..."
    )

    try:
        history = []

        for item in chats[uid]:
            history.append({
                "role": (
                    "model"
                    if item["role"] == "assistant"
                    else "user"
                ),
                "parts": [{"text": item["content"]}],
            })

        history.append({
            "role": "user",
            "parts": [{"text": question}],
        })

        response = await generate_answer(history)
        answer = response.text

        if not answer:
            await status.edit_text(
                "⚠️ Jawab generate nahi hua. Dobara try karein."
            )
            return

        chats[uid].append({
            "role": "user",
            "content": question,
        })
        chats[uid].append({
            "role": "assistant",
            "content": answer,
        })

        chunks = [
            answer[i:i + 4000]
            for i in range(0, len(answer), 4000)
        ]

        await status.edit_text(chunks[0])

        for chunk in chunks[1:]:
            await update.message.reply_text(chunk)

    except Exception as e:
        logging.exception("MathsGPT solve failed")

        error = str(e).upper()

        if "429" in error or "RESOURCE_EXHAUSTED" in error:
            message = (
                "⏳ Gemini API limit poori ho gayi hai. "
                "Kuch der baad try karein."
            )
        elif "503" in error or "UNAVAILABLE" in error:
            message = (
                "⚠️ Gemini server busy hai. "
                "Kuch der baad dobara try karein."
            )
        elif "403" in error or "PERMISSION_DENIED" in error:
            message = (
                "⚠️ API permission ya quota configuration check karein."
            )
        elif "404" in error or "NOT_FOUND" in error:
            message = (
                "⚠️ Gemini model nahi mila. "
                "GEMINI_MODEL setting check karein."
            )
        else:
            message = (
                "⚠️ Jawab nahi mil saka. "
                "Logs mein asli error check karein."
            )

        await status.edit_text(message)


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, solve)
    )

    logging.info("Starting MathsGPT with model %s", MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()