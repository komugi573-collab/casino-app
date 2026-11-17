import os
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import TelegramError
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

# Do not log Telegram updates or sender profile information.
logging.basicConfig(level=logging.WARNING)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
DB_PATH = Path(os.getenv("SUPPORT_DB_PATH", "support.sqlite3"))

PROJECT, CATEGORY, MESSAGE, VERSION, DEVICE, STEPS, ATTACHMENT, CONFIRM = range(8)



def db_connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT UNIQUE,
                recipient_chat_id INTEGER,
                project TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                answered_at TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reply_prompts (
                prompt_message_id INTEGER PRIMARY KEY,
                ticket_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_reference) REFERENCES tickets(reference)
            )"""
        )


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_ticket(recipient_chat_id: int, project: str, category: str) -> str:
    prefix = "CA" if project == "Chicken Archer" else "FL"
    with db_connect() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (recipient_chat_id, project, category, created_at) VALUES (?, ?, ?, ?)",
            (recipient_chat_id, project, category, now_iso()),
        )
        ticket_id = cur.lastrowid
        reference = f"{prefix}-{ticket_id:06d}"
        conn.execute("UPDATE tickets SET reference = ? WHERE id = ?", (reference, ticket_id))
    return reference


def get_ticket(reference: str):
    with db_connect() as conn:
        return conn.execute(
            "SELECT reference, recipient_chat_id, project, category, status FROM tickets WHERE reference = ?",
            (reference,),
        ).fetchone()


def set_ticket_status(reference: str, status: str):
    with db_connect() as conn:
        conn.execute("UPDATE tickets SET status = ? WHERE reference = ?", (status, reference))


def discard_ticket_recipient(reference: str):
    with db_connect() as conn:
        conn.execute(
            "UPDATE tickets SET status = 'delivery_failed', recipient_chat_id = NULL WHERE reference = ?",
            (reference,),
        )


def save_reply_prompt(prompt_message_id: int, reference: str):
    with db_connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO reply_prompts (prompt_message_id, ticket_reference, created_at) VALUES (?, ?, ?)",
            (prompt_message_id, reference, now_iso()),
        )


def get_reply_prompt(prompt_message_id: int):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT ticket_reference FROM reply_prompts WHERE prompt_message_id = ?",
            (prompt_message_id,),
        ).fetchone()
        return row["ticket_reference"] if row else None


def delete_reply_prompt(prompt_message_id: int):
    with db_connect() as conn:
        conn.execute("DELETE FROM reply_prompts WHERE prompt_message_id = ?", (prompt_message_id,))


def mark_ticket_answered(reference: str):
    # Erase the recipient chat ID after successful delivery; keep only ticket metadata.
    with db_connect() as conn:
        conn.execute(
            "UPDATE tickets SET status = 'answered', recipient_chat_id = NULL, answered_at = ? WHERE reference = ?",
            (now_iso(), reference),
        )


def project_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐔 Chicken Archer", callback_data="project:Chicken Archer")],
        [InlineKeyboardButton("🔥 FLAME", callback_data="project:FLAME")],
    ])


def category_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Предложение", callback_data="category:Предложение")],
        [InlineKeyboardButton("🐛 Сообщить об ошибке", callback_data="category:Ошибка")],
        [InlineKeyboardButton("📝 Другое", callback_data="category:Другое")],
    ])


def skip_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Пропустить", callback_data="skip")]
    ])


def confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить", callback_data="send")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет! Это приёмная разработчика Chicken Archer и FLAME.\n\n"
        "Здесь можно предложить новую функцию, сообщить об ошибке или оставить другое обращение.\n\n"
        "Для возможного ответа бот временно сохраняет технический ID чата, чтобы доставить тебе сообщение. "
        "Он не показывается в уведомлении об обращении и используется только для отправки ответа.\n\n"
        "Telegram также технически обрабатывает сообщения. Не указывай в обращении личные данные.\n\n"
        "Выбери проект:",
        reply_markup=project_keyboard(),
    )
    return PROJECT


async def choose_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["project"] = query.data.split(":", 1)[1]
    await query.edit_message_text("Что хочешь отправить?", reply_markup=category_keyboard())
    return CATEGORY


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data.split(":", 1)[1]
    await query.edit_message_text("Напиши обращение одним сообщением. Не указывай личные данные.")
    return MESSAGE


async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Пожалуйста, отправь текстовое описание.")
        return MESSAGE
    if len(text) > 3500:
        await update.message.reply_text("Слишком длинное сообщение. Максимум – 3500 символов.")
        return MESSAGE

    context.user_data["message"] = text
    context.user_data.setdefault("version", "Не указана")
    context.user_data.setdefault("device", "Не указано")
    context.user_data.setdefault("steps", "Не указаны")
    await update.message.reply_text(
        "Укажи версию игры/приложения (например, 3.0) или пропусти.",
        reply_markup=skip_keyboard(),
    )
    return VERSION


async def receive_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["version"] = (update.message.text or "").strip()[:100] or "Не указана"
    await update.message.reply_text(
        "На каком устройстве возникла ситуация? Например: Android, Windows. Или пропусти.",
        reply_markup=skip_keyboard(),
    )
    return DEVICE


async def receive_device(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["device"] = (update.message.text or "").strip()[:150] or "Не указано"
    await update.message.reply_text(
        "Если это ошибка, напиши шаги, после которых она появляется. Иначе пропусти.",
        reply_markup=skip_keyboard(),
    )
    return STEPS


async def receive_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["steps"] = (update.message.text or "").strip()[:1000] or "Не указаны"
    await update.message.reply_text(
        "Можешь прикрепить одно фото или короткое видео. Если вложение не нужно, нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Без вложения", callback_data="no_media")]
        ]),
    )
    return ATTACHMENT


async def skip_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["version"] = "Не указана"
    await query.edit_message_text(
        "На каком устройстве возникла ситуация? Например: Android, Windows. Или пропусти.",
        reply_markup=skip_keyboard(),
    )
    return DEVICE


async def skip_device(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["device"] = "Не указано"
    await query.edit_message_text(
        "Если это ошибка, напиши шаги, после которых она появляется. Иначе пропусти.",
        reply_markup=skip_keyboard(),
    )
    return STEPS


async def skip_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["steps"] = "Не указаны"
    await query.edit_message_text(
        "Можешь прикрепить одно фото или короткое видео. Если не нужно, нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Без вложения", callback_data="no_media")]
        ]),
    )
    return ATTACHMENT


async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("Обращение отменено. Чтобы начать заново, отправь /start.")
        return ConversationHandler.END

    data = context.user_data
    recipient_chat_id = update.effective_chat.id
    project = data.get("project", "—")
    category = data.get("category", "—")
    reference = create_ticket(recipient_chat_id, project, category)

    report = (
        f"📩 Новое анонимное обращение #{reference}\n\n"
        f"Проект: {project}\n"
        f"Категория: {category}\n"
        f"Текст: {data.get('message', '—')}\n\n"
        f"Версия: {data.get('version', 'Не указана')}\n"
        f"Устройство: {data.get('device', 'Не указано')}\n"
        f"Шаги: {data.get('steps', 'Не указаны')}"
    )
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Ответить", callback_data=f"reply:{reference}")]
    ])

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=report,
            reply_markup=reply_markup,
        )
    except TelegramError as exc:
        discard_ticket_recipient(reference)
        logger.warning("Admin notification failed for %s (%s)", reference, type(exc).__name__)
        await query.edit_message_text("Не удалось отправить обращение. Попробуй позже.")
        context.user_data.clear()
        return ConversationHandler.END

    media = data.get("media")
    if media:
        media_type, file_id = media
        try:
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID, photo=file_id, caption=f"Вложение к обращению #{reference}"
                )
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=ADMIN_CHAT_ID, video=file_id, caption=f"Вложение к обращению #{reference}"
                )
        except TelegramError as exc:
            logger.warning("Attachment delivery failed for %s (%s)", reference, type(exc).__name__)

    context.user_data.clear()
    await query.edit_message_text(
        f"✅ Твоё обращение #{reference} успешно отправлено!\n\n"
        "Спасибо за помощь в развитии проектов ❤️\n"
        "Если разработчик ответит, бот доставит ответ сюда."
    )
    return ConversationHandler.END

async def receive_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.photo:
        context.user_data["media"] = ("photo", message.photo[-1].file_id)
    elif message.video:
        if message.video.file_size and message.video.file_size > 20 * 1024 * 1024:
            await message.reply_text("Видео слишком большое. Максимальный размер – 20 МБ.")
            return ATTACHMENT
        context.user_data["media"] = ("video", message.video.file_id)
    else:
        await message.reply_text("Отправь фото/видео или нажми «Без вложения».")
        return ATTACHMENT

    await message.reply_text("Вложение добавлено. Отправить обращение?", reply_markup=confirm_keyboard())
    return CONFIRM


async def no_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Отправить обращение?", reply_markup=confirm_keyboard())
    return CONFIRM


async def begin_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_CHAT_ID or not query.message or query.message.chat_id != ADMIN_CHAT_ID:
        await query.answer("Нет доступа.", show_alert=True)
        return

    reference = query.data.split(":", 1)[1]
    ticket = get_ticket(reference)
    if not ticket or not ticket["recipient_chat_id"]:
        await query.answer("Получатель для этого обращения больше недоступен.", show_alert=True)
        return

    await query.answer()
    prompt = await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"✍️ Напиши ответ для обращения #{reference} одним сообщением.\n"
            "Нажми «Ответить» на это сообщение и отправь текст."
        ),
        reply_markup=ForceReply(selective=True, input_field_placeholder="Текст ответа..."),
    )
    save_reply_prompt(prompt.message_id, reference)


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not update.effective_user or not update.effective_chat:
        return
    if update.effective_user.id != ADMIN_CHAT_ID or update.effective_chat.id != ADMIN_CHAT_ID:
        return
    if not message.reply_to_message:
        return

    prompt_message_id = message.reply_to_message.message_id
    reference = get_reply_prompt(prompt_message_id)
    if not reference:
        return

    reply_text = (message.text or "").strip()
    if not reply_text:
        await message.reply_text("Ответ должен содержать текст. Ответь на сообщение-подсказку ещё раз.")
        return
    if len(reply_text) > 3500:
        await message.reply_text("Ответ слишком длинный. Максимум – 3500 символов.")
        return

    ticket = get_ticket(reference)
    if not ticket or not ticket["recipient_chat_id"]:
        delete_reply_prompt(prompt_message_id)
        await message.reply_text("Не удалось найти получателя этого обращения.")
        return

    try:
        await context.bot.send_message(
            chat_id=ticket["recipient_chat_id"],
            text=(
                f"📩 Разработчик ответил на твоё обращение #{reference}:\n\n"
                f"{reply_text}\n\n"
                "Спасибо, что помогаешь развивать Chicken Archer и FLAME! ❤️"
            ),
        )
    except TelegramError as exc:
        delete_reply_prompt(prompt_message_id)
        logger.warning("Reply delivery failed for %s (%s)", reference, type(exc).__name__)
        await message.reply_text(
            f"⚠️ Не удалось доставить ответ по обращению #{reference}. "
            "Возможно, пользователь заблокировал бота. Нажми «Ответить» под обращением, чтобы попробовать снова."
        )
        return

    mark_ticket_answered(reference)
    delete_reply_prompt(prompt_message_id)
    await message.reply_text(
        f"✅ Ответ по обращению #{reference} доставлен. Связь с отправителем удалена из базы."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Операция отменена. Чтобы начать заново, отправь /start.")
    return ConversationHandler.END


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PROJECT: [CallbackQueryHandler(choose_project, pattern=r"^project:")],
            CATEGORY: [CallbackQueryHandler(choose_category, pattern=r"^category:")],
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message)],
            VERSION: [
                CallbackQueryHandler(skip_version, pattern=r"^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_version),
            ],
            DEVICE: [
                CallbackQueryHandler(skip_device, pattern=r"^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_device),
            ],
            STEPS: [
                CallbackQueryHandler(skip_steps, pattern=r"^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_steps),
            ],
            ATTACHMENT: [
                CallbackQueryHandler(no_media, pattern=r"^no_media$"),
                MessageHandler(filters.PHOTO | filters.VIDEO, receive_attachment),
            ],
            CONFIRM: [
                CallbackQueryHandler(send_preview, pattern=r"^(send|cancel)$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
    )

    app.add_handler(CallbackQueryHandler(begin_admin_reply, pattern=r"^reply:"))
    app.add_handler(
        MessageHandler(
            filters.Chat(ADMIN_CHAT_ID) & filters.REPLY & filters.TEXT & ~filters.COMMAND,
            handle_admin_reply,
        )
    )
    app.add_handler(conversation)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
