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

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# =========================
# API CONFIGURATION
# =========================

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

DEFAULT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)

# =========================
# CREATOR INFORMATION
# =========================

CREATOR_NAME = "Imran"

TELEGRAM_USERNAME = "@Imimran16"
TELEGRAM_LINK = "https://t.me/Imimran16"

INSTAGRAM_USERNAME = "@i_imran_533"
INSTAGRAM_LINK = (
    "https://www.instagram.com/i_imran_533"
    "?exln=MTFoYWo1cHA5Z21vdQ=="
)

# =========================
# CHAT HISTORY
# =========================

chats = defaultdict(lambda: deque(maxlen=12))
available_models = []

# =========================
# AI INSTRUCTIONS
# =========================

INSTRUCTIONS = f"""
You are MathsGPT, a friendly, intelligent and professional
AI tutor and conversational assistant.

You help students with ALL academic subjects, not only maths.

SUBJECTS:
Mathematics, Physics, Chemistry, Biology, Hindi, English,
Urdu, History, Geography, Economics, Political Science,
Computer Science, Sanskrit, Science, Social Science,
NCERT, UP Board and other school subjects.

LANGUAGE:
- Understand Hindi, Hinglish, English and Urdu.
- Reply in the language used by the user.
- Use simple Hindi or Hinglish when appropriate.
- Use natural, friendly and respectful language.
- Explain difficult concepts in an easy-to-understand way.

MATHEMATICS:
- Solve problems step by step.
- Show formulas, substitutions and calculations.
- Explain algebra, trigonometry, calculus, differentiation,
  integration, geometry and other mathematical topics.
- Clearly highlight the final answer.
- Verify calculations before responding.

PHYSICS:
- Explain concepts, laws, derivations and numerical problems.
- Include formulas, units and calculations.
- Explain the reasoning and final result.

CHEMISTRY:
- Explain organic, inorganic and physical chemistry.
- Write and balance chemical equations correctly.
- Explain reaction conditions, products and mechanisms
  when relevant.
- Never invent chemical formulas or reactions.

BIOLOGY:
- Explain genetics, ecology, cells, human physiology,
  plant biology and other biological topics.
- Use correct terminology, examples and clear explanations.

HINDI AND URDU:
- Help with grammar, poetry, prose, literature,
  meanings, summaries, translations and question answers.
- Preserve the original meaning of literary passages.
- Use natural language and correct spelling.

ENGLISH:
- Help with grammar, vocabulary, literature, comprehension,
  essays, letters, applications and translations.
- Use correct grammar and appropriate formatting.

OTHER SUBJECTS:
- Help with school subjects and general academic topics.
- Explain definitions, causes, effects, examples and concepts.
- Follow the student's class and syllabus when specified.

NORMAL CONVERSATION:
- You can also chat naturally about everyday topics.
- Respond warmly to greetings, thanks, jokes and casual talk.
- Do not turn every conversation into a lesson.
- Be friendly without being repetitive or overly formal.
- Use emojis naturally in conversation and answers.
- Suitable emojis include 😊, 👋, 📚, 🧠, ✨, 🎯 and ✅.
- Use emojis sparingly and appropriately, not in every sentence.
- Keep serious or sensitive answers respectful.

ANSWER QUALITY AND FINISHING:
- Provide complete, accurate and polished answers.
- Never intentionally stop in the middle of an explanation.
- Answer every part of a multi-part question.
- Use headings and numbered steps when helpful.
- Avoid unnecessary introductions, filler and repetition.
- For numerical problems, show the working and final answer.
- For theory questions, explain the topic in an organized way.
- Finish long answers with a useful conclusion or summary.
- Keep short answers concise but complete.
- Do not ask an unnecessary follow-up at the end of every reply.
- If information is missing, ask a specific clarification.
- If uncertain, acknowledge the uncertainty instead of guessing.
- Never claim that an unverified answer is guaranteed correct.

FORMATTING:
- Use readable paragraphs and appropriate headings.
- Use mathematical notation when necessary.
- Highlight important results.
- For numerical questions, finish with:
  "अतः अंतिम उत्तर: ..."
  or "Final Answer: ..."
- Match the requested answer length.
- Use emojis where they genuinely improve readability.

CREATOR INFORMATION:
The creator of MathsGPT is Imran.
Telegram: {TELEGRAM_USERNAME}
Telegram link: {TELEGRAM_LINK}
Instagram: {INSTAGRAM_USERNAME}
Instagram link: {INSTAGRAM_LINK}

If anyone asks who created, built, developed, programmed
or owns this bot, identify Imran as its creator.
Provide his Telegram and Instagram links when appropriate.
Do not invent other creator details.

FINAL PRIORITIES:
Accuracy, helpfulness, friendly conversation, clear explanations,
complete answers and proper finishing.
Support all academic subjects, not mathematics alone.
"""

# =========================
# CREATOR QUESTION DETECTOR
# =========================

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
        r"\b(kisne|kis\s+ne)\s+banaya\s+hai\b",
        r"\b(banane\s+wala|banane\s+wale|banane\s+vale)\b",
        r"\b(aapko|tumko|isko|ise)\s+kisne\s+banaya\b",
        r"\bwho\s+is\s+imran\b",
        r"\b(telegram|instagram)\s+(username|id|link)\b",
    ]

    if any(re.search(pattern, text) for pattern in patterns):
        return True

    if re.search(r"\b(imimran16|i_imran_533)\b", text):
        return True

    return False


def creator_message():
    return (
        "<b>MathsGPT Creator</b>\n\n"
        "<b>Name:</b> Imran\n\n"
        f'<b>Telegram:</b> '
        f'<a href="{TELEGRAM_LINK}">{TELEGRAM_USERNAME}</a>\n\n'
        f'<b>Instagram:</b> '
        f'<a href="{INSTAGRAM_LINK}">{INSTAGRAM_USERNAME}</a>'
    )


# =========================
# MODEL DISCOVERY
# =========================

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

            # Skip specialized models unsuitable for ordinary
            # text-based educational answers.
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

        # Prefer the configured model, then Flash models.
        discovered = list(dict.fromkeys(discovered))

        discovered.sort(
            key=lambda name: (
                0 if name == DEFAULT_MODEL else 1,
                0 if "flash" in name.lower() else 1,
                name,
            )
        )

        available_models = discovered

        logging.info(
            "Available text-generation models: %s",
            available_models,
        )

        if not available_models:
            logging.error("No text-generation models found.")

    except Exception:
        logging.exception("Could not list Gemini models")

        # Fallback if model discovery fails.
        available_models = [DEFAULT_MODEL]


# =========================
# TELEGRAM COMMANDS
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Welcome to MathsGPT! 👋\n\n"
        "Main aapka AI study assistant hoon. 📚\n\n"
        "Main Maths, Physics, Chemistry, Biology, Hindi, "
        "English, Urdu aur doosre subjects mein madad kar sakta hoon.\n\n"
        "Aap apna sawal bhejiye. 🧠\n\n"
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

    await update.message.reply_text(
        "Chat history reset ho gayi! ✅"
    )


# =========================
# GEMINI ANSWER GENERATION
# =========================

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
                    logging.info(
                        "Answer generated using %s",
                        model,
                    )
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

                invalid_model = (
                    "404" in error_text
                    or "NOT_FOUND" in error_text
                    or "INVALID_ARGUMENT" in error_text
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

                # Skip unavailable or incompatible models.
                if invalid_model:
                    break

                if not temporary:
                    raise

                if attempt == 0:
                    await asyncio.sleep(2)

    if last_error:
        raise last_error

    raise RuntimeError("No usable Gemini text model found")


# =========================
# MESSAGE HANDLER
# =========================

async def solve(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    question = update.message.text.strip()

    if not question:
        return

    # Answer creator questions without using the AI API.
    if is_creator_question(question):
        await update.message.reply_text(
            creator_message(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    if len(question) > 4000:
        await update.message.reply_text(
            "Please send a shorter message (maximum 4000 characters)."
        )
        return

    # Keep the requested status text without an emoji.
    status = await update.message.reply_text(
        "GPT is Thinking..."
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
                "Jawab generate nahi ho saka. Please try again."
            )
            return

        # Save conversation only after successful generation.
        chats[uid].append({
            "role": "user",
            "content": question,
        })

        chats[uid].append({
            "role": "assistant",
            "content": answer,
        })

        # Telegram text message limit is 4096 characters.
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

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):
            message = (
                "API request limit reached. "
                "Please try again later. ⏳"
            )

        elif (
            "503" in error_text
            or "UNAVAILABLE" in error_text
        ):
            message = (
                "AI service is temporarily busy. "
                "Please try again shortly. ⏳"
            )

        elif (
            "403" in error_text
            or "PERMISSION_DENIED" in error_text
        ):
            message = (
                "API permission or quota needs checking. "
                "Please contact the bot administrator."
            )

        else:
            message = (
                "Sorry, jawab generate nahi ho saka. "
                "Please try again. 🙏"
            )

        await status.edit_text(message)


# =========================
# APPLICATION STARTUP
# =========================

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