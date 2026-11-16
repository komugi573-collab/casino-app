import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

# Do not log Telegram updates or sender profile information.
logging.basicConfig(level=logging.WARNING)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

PROJECT, CATEGORY, MESSAGE, VERSION, DEVICE, STEPS, ATTACHMENT, CONFIRM = range(8)


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
        "Разработчик не получает твои имя, username или Telegram ID. "
        "Telegram технически обрабатывает сообщения, поэтому абсолютная анонимность "
        "от самой платформы не гарантируется. Не указывай в обращении личные данные.\n\n"
        "Выбери проект:",
        reply_markup=project_keyboard(),
    )
    return PROJECT


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This returns only the ID of the person who invoked the command, to configure the bot owner.
    await update.message.reply_text(
        f"ID этого чата: {update.effective_chat.id}",
    )


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
    report = (
        "📩 Новое анонимное обращение\n\n"
        f"Проект: {data.get('project', '—')}\n"
        f"Категория: {data.get('category', '—')}\n"
        f"Текст: {data.get('message', '—')}\n\n"
        f"Версия: {data.get('version', 'Не указана')}\n"
        f"Устройство: {data.get('device', 'Не указано')}\n"
        f"Шаги: {data.get('steps', 'Не указаны')}"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=report)
        media = data.get("media")
        if media:
            media_type, file_id = media
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=ADMIN_CHAT_ID, photo=file_id, caption="Вложение к обращению"
                )
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=ADMIN_CHAT_ID, video=file_id, caption="Вложение к обращению"
                )
    except Exception:
        # No user identifiers or raw update objects are written to logs.
        await query.edit_message_text("Не удалось отправить обращение. Попробуй позже.")
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "✅ Твоё обращение успешно отправлено!\n\n"
        "Спасибо за помощь в развитии проектов ❤️\n"
        "Каждая идея и найденная ошибка важны!"
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

    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(conversation)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
