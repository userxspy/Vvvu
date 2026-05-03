import asyncio
import re
import math
import random
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from info import ADMINS, DELETE_TIME, MAX_BTN, IS_PREMIUM, PICS, IS_STREAM
from utils import is_premium, get_size, is_check_admin, temp, get_settings, save_group_settings
from database.ia_filterdb import get_search_results

# ─────────────────────────────────────────────
# ⚡ GLOBAL CACHE (Auto-Cleaner Optimized)
# ─────────────────────────────────────────────
BUTTONS = {}

def check_cache_limit():
    if len(BUTTONS) > 500:
        keys_to_delete = list(BUTTONS.keys())[:100]
        for k in keys_to_delete:
            BUTTONS.pop(k, None)
            temp.FILES.pop(k, None)

# ─────────────────────────────────────────────
# 🛠️ VALIDATOR
# ─────────────────────────────────────────────
async def is_valid_search(message):
    if not message.text or message.text.startswith("/"):
        return False
    if message.forward_date or message.photo or message.video or message.document:
        return False
    if message.entities:
        for entity in message.entities:
            if entity.type in [enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK]:
                return False
    if not any(c.isalnum() for c in message.text):
        return False
    return True

# ─────────────────────────────────────────────
# 🔍 PRIVATE SEARCH
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if not await is_valid_search(message):
        return

    if IS_PREMIUM and not await is_premium(message.from_user.id, client):
        return await message.reply_photo(
            random.choice(PICS),
            caption="🔒 **Premium Required**\n\nOnly Premium users can use this bot in DM.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Buy Premium", callback_data="activate_plan"),
                InlineKeyboardButton("📊 My Plan", callback_data="myplan")
            ]])
        )

    await auto_filter(client, message, collection_type="all")

# ─────────────────────────────────────────────
# 🔍 GROUP SEARCH
# ─────────────────────────────────────────────
@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    if not await is_valid_search(message):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    settings = await get_settings(chat_id)
    if not settings.get("search_enabled", True):
        return

    if IS_PREMIUM and not await is_premium(user_id, client):
        return

    text_lower = message.text.lower()

    if "@admin" in text_lower:
        if await is_check_admin(client, chat_id, user_id):
            return
        mentions = []
        async for m in client.get_chat_administrators(chat_id):
            if not m.user.is_bot:
                mentions.append(f"<a href='tg://user?id={m.user.id}'>\u2063</a>")
        await message.reply(f"✅ Report sent to admins!{''.join(mentions)}")
        return

    if "http" in text_lower or "t.me/" in text_lower:
        if re.search(r"(?:http|www\.|t\.me/)", text_lower):
            if not await is_check_admin(client, chat_id, user_id):
                try: await message.delete()
                except: pass
                msg = await message.reply("❌ Links not allowed!", quote=True)
                await asyncio.sleep(5)
                try: await msg.delete()
                except: pass
                return

    await auto_filter(client, message, collection_type="all")

# ─────────────────────────────────────────────
# ⚙️ ADMIN TOGGLE
# ─────────────────────────────────────────────
@Client.on_message(filters.command("search") & filters.group)
async def search_toggle(client, message):
    if not await is_check_admin(client, message.chat.id, message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("Usage: `/search on` or `/search off`")

    action = message.command[1].lower()
    state = True if action == "on" else False
    await save_group_settings(message.chat.id, "search_enabled", state)
    await message.reply(f"✅ Search is now **{'ENABLED' if state else 'DISABLED'}**")

# ─────────────────────────────────────────────
# 🚀 AUTO FILTER CORE
# ─────────────────────────────────────────────
SRC_TO_SHORT = {"primary": "pri", "cloud": "cld", "archive": "arc"}
SHORT_TO_SRC = {"pri": "primary", "cld": "cloud", "arc": "archive"}

async def auto_filter(client, msg, collection_type="all"):
    check_cache_limit() 

    search = msg.text.strip()
    
    files, next_offset, total, actual_source = await get_search_results(
        search, max_results=MAX_BTN, offset=0, collection_type=collection_type
    )

    if not files:
        try:
            m = await msg.reply(f"❌ No results for <b>{search}</b>", quote=True)
            await asyncio.sleep(5)
            await m.delete()
        except: pass
        return

    key = f"{msg.chat.id}-{msg.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search

    list_items = []
    for file in files:
        f_link = f"https://t.me/{temp.U_NAME}?start=file_{msg.chat.id}_{file['_id']}"
        list_items.append(
            f"📁 <a href='{f_link}'>[{get_size(file['file_size'])}] {file['file_name']}</a>"
        )
    
    files_text = "\n\n".join(list_items)
    total_pages = math.ceil(total / MAX_BTN)
    
    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {actual_source.upper()}\n"
        f"📄 Page: 1/{total_pages}</b>\n\n"
        f"{files_text}"
    )

    btn = []
    act_src_short = SRC_TO_SHORT.get(actual_source, "pri")
    
    if total <= MAX_BTN:
        btn.append([InlineKeyboardButton("📤 Send All", callback_data=f"sendall_{msg.from_user.id}_{key}_{act_src_short}")])
    else:
        nav = [InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="pages")]
        if next_offset:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"nav_{msg.from_user.id}_{key}_{next_offset}_{act_src_short}"))
        btn.append(nav)

    col_btn = []
    for c in ["primary", "cloud", "archive"]:
        tick = "✅" if c == actual_source else "📂"
        c_short = SRC_TO_SHORT[c]
        col_btn.append(InlineKeyboardButton(f"{tick} {c.title()}", callback_data=f"coll_{msg.from_user.id}_{key}_{c_short}"))
    btn.append(col_btn)

    btn.append([InlineKeyboardButton("❌ Close", callback_data=f"close_{msg.from_user.id}")])

    try:
        m = await msg.reply(cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, quote=True)
        settings = await get_settings(msg.chat.id)
        if settings.get("auto_delete"):
            asyncio.create_task(auto_delete_msg(m, msg))
    except Exception as e:
        print(f"Error sending filter: {e}")

async def auto_delete_msg(bot_msg, user_msg):
    await asyncio.sleep(DELETE_TIME)
    try: await bot_msg.delete()
    except: pass
    try: await user_msg.delete()
    except: pass

# ─────────────────────────────────────────────
# 📤 SEND ALL HANDLER (With Stream Buttons)
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^sendall_"))
async def send_all_handler(client, query):
    try:
        _, req, key, coll_short = query.data.split("_", 3)
        if int(req) != query.from_user.id:
            return await query.answer("❌ This is not your search!", show_alert=True)
    except:
        return await query.answer("❌ Error!", show_alert=True)

    if IS_PREMIUM and not await is_premium(query.from_user.id, client):
        return await query.answer("❌ Premium Expired!", show_alert=True)

    files = temp.FILES.get(key)
    if not files:
        return await query.answer("❌ Search Expired! Search again.", show_alert=True)

    await query.answer("📤 Sending files to your PM...", show_alert=False)

    try:
        await client.send_message(query.from_user.id, f"<b>📥 All files for your search:</b>")
        for file in files:
            target_id = file.get("file_ref") or file.get("file_id")
            if not target_id or str(target_id).strip() == 'None':
                continue
            
            cap_template = '{file_name}\n\n💾 Size: {file_size}'
            caption = cap_template.replace('{file_name}', str(file.get('file_name', 'File')))\
                                  .replace('{file_size}', get_size(file.get('file_size', 0)))
            
            # ✅ Watch/Download Button Logic
            btn = [[InlineKeyboardButton('❌ Close', callback_data=f'close_{query.from_user.id}')]]
            if IS_STREAM:
                btn.insert(0, [InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{target_id}")])
            
            await client.send_cached_media(
                chat_id=query.from_user.id,
                file_id=target_id,
                caption=caption,
                reply_markup=InlineKeyboardMarkup(btn)
            )
            await asyncio.sleep(0.5) 
            
    except Exception as e:
        if "USER_IS_BLOCKED" in str(e) or "PEER_ID_INVALID" in str(e):
            await query.message.reply(
                f"❌ <a href='tg://user?id={query.from_user.id}'>User</a>, please start me in PM first to receive files!\n\n👉 t.me/{getattr(temp, 'U_NAME', 'bot')}?start=start", 
                disable_web_page_preview=True
            )
        print(f"Send All Error: {e}")

# ─────────────────────────────────────────────
# 🔁 NAVIGATION HANDLER
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^nav_"))
async def nav_handler(client, query):
    try:
        _, req, key, offset, coll_short = query.data.split("_", 4)
        if int(req) != query.from_user.id:
            return await query.answer("❌ Not for you!", show_alert=True)
    except:
        return await query.answer("❌ Error!", show_alert=True)

    if IS_PREMIUM and not await is_premium(query.from_user.id, client):
        return await query.answer("❌ Premium Expired!", show_alert=True)

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("❌ Search Expired! Search again.", show_alert=True)

    coll_type = SHORT_TO_SRC.get(coll_short, "primary")

    files, next_off, total, act_src = await get_search_results(
        search, max_results=MAX_BTN, offset=int(offset), collection_type=coll_type
    )
    if not files: return await query.answer("❌ No more pages!", show_alert=True)

    temp.FILES[key] = files

    list_items = []
    for file in files:
        f_link = f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file['_id']}"
        list_items.append(f"📁 <a href='{f_link}'>[{get_size(file['file_size'])}] {file['file_name']}</a>")
    
    files_text = "\n\n".join(list_items)
    total_pages = math.ceil(total / MAX_BTN)
    curr_page = (int(offset) // MAX_BTN) + 1
    
    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {act_src.upper()}\n"
        f"📄 Page: {curr_page}/{total_pages}</b>\n\n"
        f"{files_text}"
    )

    btn = []
    nav = []
    prev_off = int(offset) - MAX_BTN
    act_src_short = SRC_TO_SHORT.get(act_src, "pri")
    
    if prev_off >= 0:
        nav.append(InlineKeyboardButton("« Prev", callback_data=f"nav_{req}_{key}_{prev_off}_{act_src_short}"))
    
    nav.append(InlineKeyboardButton(f"📄 {curr_page}/{total_pages}", callback_data="pages"))
    
    if next_off:
        nav.append(InlineKeyboardButton("Next »", callback_data=f"nav_{req}_{key}_{next_off}_{act_src_short}"))
    btn.append(nav)

    col_btn = []
    for c in ["primary", "cloud", "archive"]:
        tick = "✅" if c == act_src else "📂"
        c_short = SRC_TO_SHORT[c]
        col_btn.append(InlineKeyboardButton(f"{tick} {c.title()}", callback_data=f"coll_{req}_{key}_{c_short}"))
    btn.append(col_btn)
    
    btn.append([InlineKeyboardButton("❌ Close", callback_data=f"close_{req}")])

    try:
        await query.message.edit_text(cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)
    except:
        pass
    await query.answer()

# ─────────────────────────────────────────────
# 🗂️ COLLECTION SWITCH
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^coll_"))
async def coll_handler(client, query):
    try:
        _, req, key, coll_short = query.data.split("_", 3)
        if int(req) != query.from_user.id:
            return await query.answer("❌ Not for you!", show_alert=True)
    except:
        return

    if IS_PREMIUM and not await is_premium(query.from_user.id, client):
        return await query.answer("❌ Premium Expired!", show_alert=True)

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("❌ Search Expired!", show_alert=True)

    coll_type = SHORT_TO_SRC.get(coll_short, "primary")

    files, next_off, total, act_src = await get_search_results(
        search, max_results=MAX_BTN, offset=0, collection_type=coll_type
    )
    if not files:
        return await query.answer(f"❌ No files in {coll_type.upper()}", show_alert=True)

    temp.FILES[key] = files

    list_items = []
    for file in files:
        f_link = f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file['_id']}"
        list_items.append(f"📁 <a href='{f_link}'>[{get_size(file['file_size'])}] {file['file_name']}</a>")
    
    files_text = "\n\n".join(list_items)
    total_pages = math.ceil(total / MAX_BTN)
    
    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {act_src.upper()}\n"
        f"📄 Page: 1/{total_pages}</b>\n\n"
        f"{files_text}"
    )

    btn = []
    act_src_short = SRC_TO_SHORT.get(act_src, "pri")

    if total <= MAX_BTN:
        btn.append([InlineKeyboardButton("📤 Send All", callback_data=f"sendall_{req}_{key}_{act_src_short}")])
    else:
        nav = [InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="pages")]
        if next_off:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"nav_{req}_{key}_{next_off}_{act_src_short}"))
        btn.append(nav)

    col_btn = []
    for c in ["primary", "cloud", "archive"]:
        tick = "✅" if c == act_src else "📂"
        c_short = SRC_TO_SHORT[c]
        col_btn.append(InlineKeyboardButton(f"{tick} {c.title()}", callback_data=f"coll_{req}_{key}_{c_short}"))
    btn.append(col_btn)
    
    btn.append([InlineKeyboardButton("❌ Close", callback_data=f"close_{req}")])

    try:
        await query.message.edit_text(cap, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)
    except:
        pass
    await query.answer()

@Client.on_callback_query(filters.regex(r"^close_"))
async def close_cb(c, q):
    try:
        req_id = int(q.data.split("_")[1])
        if req_id != q.from_user.id:
            return await q.answer("❌ This is not your search!", show_alert=True)
        await q.message.delete()
    except Exception:
        pass

@Client.on_callback_query(filters.regex("^pages$"))
async def pages_cb(c, q):
    await q.answer()
