import os
import asyncio
import logging
import re
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

# API configuration
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Creator information
CREATOR_NAME = "Imran"
TELEGRAM_USERNAME = "@Imimran16"
TELEGRAM_LINK = "https://t.me/Imimran16"
INSTAGRAM_USERNAME = "@i_imran_533"
INSTAGRAM_LINK = (
    "https://www.instagram.com/i_imran_533"
    "?exln=MTFoYWo1cHA5Z21vdQ=="
)

chats = defaultdict(lambda: deque(maxlen=12))
available_models = []

INSTRUCTIONS = f"""
You are MathsGPT, a mathematics tutor for Class 11 and 12.
Help students with NCERT and UP Board mathematics.

Explain solutions step by step in simple Hindi or Hinglish
when the student writes in Hindi or Hinglish.
Show formulas, calculations and the final answer.
If a question is unclear, ask for clarification.
Never invent a mathematical result.

CREATOR INFORMATION:
The creator of MathsGPT is {CREATOR_NAME}.
Telegram: {TELEGRAM_USERNAME} ({TELEGRAM_LINK})
Instagram: {INSTAGRAM_USERNAME} ({INSTAGRAM_LINK})

If anyone asks who made, created, developed, built, owns,
or programmed this bot, identify Imran as its creator.
Provide his Telegram and Instagram links when asked.
Do not claim that another person created this bot.
"""


def is_creator_question(text):
    text = text.lower()

    patterns = [
        r"\bwho\s+(made|created|built|developed|programmed|owns?)\b",
        r"\bwho\s+(is|are)\s+(the\s+)?(creator|developer|maker|owner)\b",
        r"\b(your|bot'?s|mathsgpt'?s)\s+(creator|developer|maker|owner)\b",
        r"\b(creator|developer|maker|owner)\s+(name|details|contact)\b",
        r"\b(kisne|kis\s+ne)\s+(banaya|banai|develop|create|program)\b",
        r"\b(kisne|kis\s+ne)\s+banaya\s+hai\b",
        r"\b(banane\s+wala|banane\s+wale|banane\s+vale)\b",
        r"\b(aapko|tumko|isko|ise)\s+kisne\s+banaya\b",
        r"\bwho\s+is\s+imran\b",
        r"\b(telegram|instagram)\s+(username|id|link)\b",
        r"\b(imimran16|i_imran_533)\b",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def creator_message():
    return (
        "<b>MathsGPT Creator</b>\n\n"
        "<b>Name:</b> Imran\n\n"
        f'<b>Telegram:</b> '
        f'<a href="{TELEGRAM_LINK}">{TELEGRAM_USERNAME}</a>\n\n'
        f'<b>Instagram:</b> '
        f'<a href="{INSTAGRAM_LINK}">{INSTAGRAM_USERNAME}</a>'
    )


async def load_models():
    global available_models

    try:
        pager = await client.aio.models.list()
        discovered = []

        async for model in pager:
            name = (model.name or "").replace("models/", "")
            actions = model.supported_actions or []

            if "generateContent" not in actions:
                continue

            # Exclude audio-only and specialized models.
            excluded = (
                "tts",
                "live",
                "transcribe",
                "embedding",
                "image",
                "robotics",
                "computer-use",
            )

            if any(word in name.lower() for word in excluded):
                continue

            discovered.append(name)

        # Prefer Flash models for quick maths answers.
        discovered.sort(
            key=lambda name: (
                0 if "flash" in name.lower() else 1,
                0 if name == DEFAULT_MODEL else 1,
                name,
            )
        )

        available_models = list(dict.fromkeys(discovered))

        if DEFAULT_MODEL in available_models:
            available_models.remove(DEFAULT_MODEL)
            available_models.insert(0, DEFAULT_MODEL)

        logging.info("Available text models: %s", available_models)

        if not available_models:
            logging.error("No text-generation models found.")

    except Exception:
        logging.exception("Could not list Gemini models")
        available_models = [DEFAULT_MODEL]


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Welcome to MathsGPT!\n\n"
        "Main Class 11 aur 12 Maths ke sawal "
        "step-by-step solve karta hoon.\n\n"
        "Apna sawal bhejein.\n\n"
        "/reset - Chat history clear karein\n"
        "/creator - Creator details"
    )


async def creator_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        creator_message(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chats.pop(update.effective_user.id, None)
    await update.message.reply_text("Chat reset ho gayi.")


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

            except Exception as error:
                last_error = error
                error_text = str(error).upper()

                logging.warning(
                    "Model %s failed: %s",
                    model,
                    error,
                )

                temporary = any(
                    code in error_text
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

                invalid_model = (
                    "404" in error_text
                    or "NOT_FOUND" in error_text
                    or "INVALID_ARGUMENT" in error_text
                )

                if invalid_model:
                    break

                if not temporary:
                    raise

                if attempt == 0:
                    await asyncio.sleep(2)

    if last_error:
        raise last_error

    raise RuntimeError("No usable Gemini text model found")


async def solve(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    uid = update.effective_user.id
    question = update.message.text.strip()

    if not question:
        return

    if len(question) > 4000:
        await update.message.reply_text(
            "Kripya 4000 characters se chhota sawal bhejein."
        )
        return

    if is_creator_question(question):
        await update.message.reply_text(
            creator_message(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    status = await update.message.reply_text("GPT is Thinking...")

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
            await status.edit_text("Jawab generate nahi ho saka.")
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

    except Exception as error:
        logging.exception("MathsGPT solve failed")

        error_text = str(error).upper()

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            message = (
                "Gemini API limit poori hai. "
                "Kuch der baad dobara try karein."
            )
        elif "503" in error_text or "UNAVAILABLE" in error_text:
            message = (
                "Gemini ke models abhi busy hain. "
                "Kuch der baad dobara try karein."
            )
        elif "403" in error_text or "PERMISSION_DENIED" in error_text:
            message = "Gemini API permission ya quota check karein."
        else:
            message = (
                "Jawab nahi mil saka. "
                "FadeHost logs mein asli error dekhein."
            )

        await status.edit_text(message)


async def post_init(application):
    await load_models()


def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("creator", creator_command))
    app.add_handler(CommandHandler("reset", reset))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            solve,
        )
    )

    logging.info("Starting MathsGPT")
    app.run_polling()


if __name__ == "__main__":
    main()