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

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

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

available_models = []


async def load_models():
    global available_models

    try:
        models = await client.aio.models.list()
        found = []

        async for model in models:
            actions = model.supported_actions or []
            name = model.name or ""

            if "generateContent" in actions and name:
                found.append(name.replace("models/", ""))

        # Configured model ko pehle try karo.
        ordered = [DEFAULT_MODEL]
        ordered.extend(found)

        available_models = list(dict.fromkeys(ordered))

        logging.info("Gemini models discovered: %s", found)
        logging.info("Models to try: %s", available_models)

    except Exception:
        logging.exception("Could not list Gemini models")
        available_models = [DEFAULT_MODEL]


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📐 Welcome to MathsGPT!\n\n"
        "Main Maths ke sawal step-by-step solve karta hoon.\n"
        "Apna sawal bhejo.\n\n"
        "/reset - Chat history clear karein"
    )


async def reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chats.pop(update.effective_user.id, None)
    await update.message.reply_text("Chat reset ho gayi! ✅")


async def generate_answer(history):
    if not available_models:
        await load_models()

    last_error = None

    for model in available_models:
        for attempt in range(2):
            try:
                logging.info(
                    "Trying model %s, attempt %s/2",
                    model,
                    attempt + 1,
                )

                response = await client.aio.models.generate_content(
                    model=model,
                    contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=INSTRUCTIONS,
                        max_output_tokens=1000,
                    ),
                )

                if response.text:
                    logging.info("Success with model: %s", model)
                    return response

                last_error = RuntimeError(
                    f"{model} returned an empty response"
                )
                break

            except Exception as e:
                last_error = e
                error = str(e).upper()

                logging.warning(
                    "Model %s failed: %s",
                    model,
                    str(e),
                )

                temporary = any(
                    code in error
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

                # Invalid model ho to doosra model try karo.
                invalid_model = (
                    "404" in error or "NOT_FOUND" in error
                )

                if not temporary and not invalid_model:
                    raise

                if temporary and attempt == 0:
                    await asyncio.sleep(2)

                if temporary and attempt == 1:
                    break

    if last_error:
        raise last_error

    raise RuntimeError("No Gemini models available")


async def solve(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    uid = update.effective_user.id
    question = update.message.text.strip()

    if len(question) > 4000:
        await update.message.reply_text(
            "Kripya 4000 characters se chhota sawal bhejein."
        )
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
                "⏳ Gemini API limit poori hai. "
                "Kuch der baad try karein."
            )
        elif "503" in error or "UNAVAILABLE" in error:
            message = (
                "⚠️ Gemini ke available models abhi busy hain. "
                "Kuch der baad try karein."
            )
        elif "403" in error or "PERMISSION_DENIED" in error:
            message = (
                "⚠️ API permission ya quota check karein."
            )
        else:
            message = (
                "⚠️ Jawab nahi mil saka. "
                "FadeHost logs mein asli error dekhein."
            )

        await status.edit_text(message)


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            solve,
        )
    )

    async def initialize(application):
        await load_models()

    app.post_init = initialize

    logging.info("Starting MathsGPT")
    app.run_polling()


if __name__ == "__main__":
    main()