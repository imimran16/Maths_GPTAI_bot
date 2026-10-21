
import os
import html
import asyncio
import logging
from collections import defaultdict

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types

# ========== CONFIG ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROMPTLENS_URL = "https://promptlens-ai-vercel.vercel.app"

CREATOR_USERNAME = "imimran16"
CREATOR_TELEGRAM = "https://t.me/Imimran16"
INSTAGRAM_1 = "https://www.instagram.com/i_imran_533/"
INSTAGRAM_2 = "https://www.instagram.com/im.imran16/"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
history = defaultdict(list)
user_tasks = {}
user_counts = defaultdict(int)


# ========== START ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton(
                "🤖 Educator AI",
                callback_data="educator",
            )
        ],
        [
            InlineKeyboardButton(
                "🔍 Open PromptLens AI",
                url=PROMPTLENS_URL,
            )
        ],
        [
            InlineKeyboardButton(
                "👨‍💻 Creator",
                callback_data="creator",
            ),
            InlineKeyboardButton(
                "🔄 Reset Chat",
                callback_data="reset",
            ),
        ],
    ]

    await update.message.reply_text(
        "👋 Welcome to Educator AI!\n\n"
        "📚 Your AI Study Assistant\n"
        "➗ Maths | ⚡ Physics | 🧪 Chemistry\n"
        "💻 Coding | 🌍 General Knowledge\n\n"
        "Apna sawal bhejo aur AI se jawab pao.\n"
        "PromptLens AI use karne ke liye neeche button dabao.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ========== BUTTONS ==========
async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "educator":
        await query.message.reply_text(
            "🤖 Educator AI ready hai!\n"
            "Apna Maths, Science, Coding ya koi bhi sawal bhejo."
        )

    elif query.data == "creator":
        keyboard = [
            [
                InlineKeyboardButton(
                    "Telegram",
                    url=CREATOR_TELEGRAM,
                )
            ],
            [
                InlineKeyboardButton(
                    "Instagram 1",
                    url=INSTAGRAM_1,
                ),
                InlineKeyboardButton(
                    "Instagram 2",
                    url=INSTAGRAM_2,
                ),
            ],
        ]
        await query.message.reply_text(
            "👨‍💻 Created by Imran\n\n"
            "Building AI tools, coding projects and learning "
            "about technology and investing.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "reset":
        history[user_id] = []
        task = user_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
        await query.message.reply_text(
            "🔄 Chat reset ho gayi! Ab naya sawal bhejo."
        )


# ========== RESET COMMAND ==========
async def reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user_id = update.effective_user.id
    history[user_id] = []

    task = user_tasks.get(user_id)
    if task and not task.done():
        task.cancel()

    await update.message.reply_text(
        "🔄 Conversation reset ho gayi!"
    )


# ========== CREATOR COMMAND ==========
async def creator_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "👨‍💻 Created by Imran\n\n"
        "Telegram: " + CREATOR_TELEGRAM + "\n"
        "Instagram: " + INSTAGRAM_1 + "\n"
        "PromptLens AI: " + PROMPTLENS_URL
    )


# ========== STATS COMMAND ==========
async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not user or (user.username or "").lower() != CREATOR_USERNAME:
        await update.message.reply_text(
            "⛔ Ye command sirf bot creator ke liye hai."
        )
        return

    await update.message.reply_text(
        f"📊 Current process mein users: {len(user_counts)}\n"
        f"💬 Total messages: {sum(user_counts.values())}"
    )


# ========== GEMINI AI ==========
async def generate_answer(user_id: int, question: str) -> str:
    if client is None:
        return (
            "⚠️ Gemini API key configure nahi hai. "
            "FadeHost ke environment variables check karo."
        )

    contents = list(history[user_id])
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=question)],
        )
    )

    try:
        response = await client.aio.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are Educator AI, a helpful assistant. "
                    "Answer accurately and clearly. "
                    "Support Hindi, Hinglish, Urdu and English. "
                    "Explain educational problems step by step."
                ),
                max_output_tokens=2048,
            ),
        )

        answer = response.text or "Maaf karna, is baar jawab nahi mil saka."

        history[user_id].append(
            types.Content(
                role="user",
                parts=[types.Part(text=question)],
            )
        )
        history[user_id].append(
            types.Content(
                role="model",
                parts=[types.Part(text=answer)],
            )
        )

        # Keep only the latest 12 conversation messages.
        history[user_id] = history[user_id][-12:]

        return answer

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Gemini request failed")
        return (
            "⚠️ AI se jawab lene mein dikkat aa gayi.\n\n"
            "FadeHost logs aur GEMINI_MODEL setting check karo."
        )


# ========== TEXT MESSAGES ==========
async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    user_id = user.id
    question = message.text.strip()

    if not question:
        return

    user_counts[user_id] += 1

    old_task = user_tasks.get(user_id)
    if old_task and not old_task.done():
        old_task.cancel()

    task = asyncio.current_task()
    user_tasks[user_id] = task

    try:
        status = await message.reply_text("GPT is Thinking...")
        answer = await generate_answer(user_id, question)

        # Telegram message limit is 4096 characters.
        chunks = [
            answer[i:i + 4000]
            for i in range(0, len(answer), 4000)
        ] or ["Jawab available nahi hai."]

        try:
            await status.delete()
        except Exception:
            pass

        for chunk in chunks:
            await message.reply_text(chunk)

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Message handler failed")
        await message.reply_text(
            "⚠️ Unexpected error. FadeHost logs check karo."
        )
    finally:
        if user_tasks.get(user_id) is task:
            user_tasks.pop(user_id, None)


# ========== ERROR HANDLER ==========
async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Telegram update error",
        exc_info=context.error,
    )


# ========== MAIN ==========
def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable missing."
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("creator", creator_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )
    app.add_error_handler(error_handler)

    logger.info("Educator AI bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
