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

# API CONFIGURATION
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# CREATOR INFORMATION
CREATOR_NAME = "Imran"
TELEGRAM_USERNAME = "@Imimran16"
TELEGRAM_LINK = "https://t.me/Imimran16"
INSTAGRAM_USERNAME = "@i_imran_533"
INSTAGRAM_LINK = (
    "https://www.instagram.com/i_imran_533"
    "?exln=MTFoYWo1cHA5Z21vdQ=="
)

# CHAT DATA
chats = defaultdict(lambda: deque(maxlen=12))
available_models = []

# Latest active request for each user
active_requests = {}


INSTRUCTIONS = f"""
You are MathsGPT, a friendly and professional AI tutor.

SUBJECTS:
Help with Mathematics, Physics, Chemistry, Biology, Hindi,
English, Urdu, History, Geography, Economics, Political Science,
Computer Science, Sanskrit and other academic subjects.

CAPABILITIES:
- Solve academic questions step by step.
- Explain formulas, calculations, concepts and theory.
- Help with grammar, essays, translations, summaries and literature.
- Explain coding, programming and general knowledge.
- Chat naturally and use appropriate emojis.
- Reply in the language used by the user.
- Give complete answers with proper finishing.
- State the final answer clearly for numerical problems.
- Ask for clarification if a question is unclear.

LIMITATIONS:
- You cannot directly perform physical-world tasks.
- You cannot guarantee every answer is correct.
- You cannot access private accounts or personal data without
  an appropriate authorized connection.
- You cannot guarantee live or latest information without
  a suitable live-data source.
- You cannot directly view photographs in this text-only bot.
- Never pretend to have performed an action you did not perform.
- If something is impossible, explain the limitation honestly
  and suggest a practical alternative.

ANSWER QUALITY:
- Use simple Hindi or Hinglish when appropriate.
- Show the necessary reasoning and calculations.
- Do not invent facts, formulas or sources.
- Avoid unnecessary repetition and filler.
- Complete all parts of the requested task.
- Do not ask unnecessary follow-up questions.
- Use appropriate emojis naturally, without overusing them.

CREATOR:
MathsGPT was created by Imran.
Telegram: {TELEGRAM_USERNAME} ({TELEGRAM_LINK})
Instagram: {INSTAGRAM_USERNAME} ({INSTAGRAM_LINK})

When asked about the creator, identify Imran and provide
his contact links. Do not invent other creator details.
"""


def is_creator_question(text):
    text = text.lower().strip()

    patterns = [
        r"\bwho\s+(made|created|built|developed|programmed)\b",
        r"\bwho\s+(is|are)\s+(the\s+)?"
        r"(creator|developer|maker|owner)\b",
        r"\b(your|bot'?s|mathsgpt'?s)\s+"
        r"(creator|developer|maker|owner)\b",
        r"\b(creator|developer|maker|owner)\s+"
        r"(name|details|contact)\b",
        r"\b(kisne|kis\s+ne)\s+"
        r"(banaya|banai|develop|create|program)\b",
        r"\b(banane\s+wala|banane\s+wale|banane\s+vale)\b",
        r"\bwho\s+is\s+imran\b",
        r"\b(telegram|instagram)\s+(username|id|link)\b",
    ]

    return (
        any(re.search(p, text) for p in patterns)
        or bool(re.search(r"\b(imimran16|i_imran_533)\b", text))
    )


def creator_message():
    return (
        "<b>MathsGPT Creator</b>\n\n"
        "<b>Name:</b> Imran\n\n"
        f'<b>Telegram:</b> '
        f'<a href="{TELEGRAM_LINK}">{TELEGRAM_USERNAME}</a>\n\n'
        f'<b>Instagram:</b> '
        f'<a href="{INSTAGRAM_LINK}">{INSTAGRAM_USERNAME}</a>'
    )


# DISCOVER AVAILABLE TEXT MODELS
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

            excluded = (
                "tts",
                "live",
                "transcribe",
                "embedding",
                "robotics",
                "computer-use",
            )

            if any(word in name.lower() for word in excluded):
                continue

            discovered.append(name)

        discovered = list(dict.fromkeys(discovered))
        discovered.sort(
            key=lambda name: (
                0 if name == DEFAULT_MODEL else 1,
                0 if "flash" in name.lower() else 1,
                name,
            )
        )

        available_models = discovered

        logging.info("Available models: %s", available_models)

    except Exception:
        logging.exception("Model discovery failed")
        available_models = [DEFAULT_MODEL]


# TELEGRAM COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to MathsGPT!\n\n"
        "Main aapka AI study assistant hoon.\n\n"
        "KYA KAR SAKTA HOON:\n"
        "- Maths, Physics, Chemistry aur Biology\n"
        "- Hindi, English, Urdu aur doosre subjects\n"
        "- Step-by-step solutions aur theory explanations\n"
        "- Grammar, translation, essays aur coding\n"
        "- General questions aur normal conversation\n\n"
        "LIMITATIONS:\n"
        "- Is version mein photo se question solve nahi hota.\n"
        "- Physical-world tasks khud perform nahi kar sakta.\n"
        "- Har answer ki 100% accuracy guarantee nahi hai.\n"
        "- Live information ke liye live-data source zaroori hai.\n\n"
        "IMPORTANT: Naya sawal bhejne par aapka purana "
        "ongoing sawal cancel ho jayega.\n\n"
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


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    # Cancel this user's active request, if any.
    task = active_requests.get(uid)
    current = asyncio.current_task()

    if task and task is not current and not task.done():
        task.cancel()

    chats.pop(uid, None)

    await update.message.reply_text(
        "Chat history reset ho gayi. Purana ongoing kaam cancel kar diya."
    )


# GEMINI REQUEST WITH FALLBACK
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
                        max_output_tokens=2000,
                    ),
                )

                if response.text:
                    logging.info("Success with model: %s", model)
                    return response

                last_error = RuntimeError(
                    f"{model} returned an empty answer"
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

                invalid_model = any(
                    code in error_text
                    for code in (
                        "404",
                        "NOT_FOUND",
                        "INVALID_ARGUMENT",
                    )
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

                if invalid_model:
                    break

                if not temporary:
                    raise

                if attempt == 0:
                    await asyncio.sleep(2)

    if last_error:
        raise last_error

    raise RuntimeError("No usable Gemini model found")


# MESSAGE HANDLER
async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    question = update.message.text.strip()

    if not question:
        return

    if len(question) > 4000:
        await update.message.reply_text(
            "Please 4000 characters se chhota sawal bhejein."
        )
        return

    # New message cancels the previous request for this user.
    current_task = asyncio.current_task()
    previous_task = active_requests.get(uid)

    if (
        previous_task
        and previous_task is not current_task
        and not previous_task.done()
    ):
        previous_task.cancel()

    active_requests[uid] = current_task
    status = None

    try:
        # Creator questions do not need Gemini.
        if is_creator_question(question):
            await update.message.reply_text(
                creator_message(),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return

        status = await update.message.reply_text("GPT is Thinking...")

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

        # Only save completed answers.
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

    except asyncio.CancelledError:
        # A newer message has replaced this request.
        if status is not None:
            try:
                await status.edit_text(
                    "Purana sawal cancel kar diya gaya. "
                    "Naye sawal par kaam ho raha hai."
                )
            except Exception:
                pass

        raise

    except Exception as error:
        logging.exception("MathsGPT solve failed")

        error_text = str(error).upper()

        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            message = "API limit poori hai. Kuch der baad try karein."
        elif "503" in error_text or "UNAVAILABLE" in error_text:
            message = "AI service busy hai. Kuch der baad try karein."
        elif "403" in error_text or "PERMISSION_DENIED" in error_text:
            message = "API permission ya quota check karein."
        else:
            message = "Jawab nahi mil saka. FadeHost logs check karein."

        if status is not None:
            try:
                await status.edit_text(message)
            except Exception:
                logging.exception("Could not update Telegram status")
        else:
            await update.message.reply_text(message)

    finally:
        # An old request must not remove the newer request.
        if active_requests.get(uid) is current_task:
            active_requests.pop(uid, None)


async def post_init(application):
    await load_models()


def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
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