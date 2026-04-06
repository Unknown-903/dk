import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import OWNER_ID, ADMINS, START_MSG, FORCE_MSG, PROTECT_CONTENT, START_PIC, FORCE_PIC, HELP_TXT, ABOUT_TXT
from helper_func import subscribed, encode, decode, get_messages, readable_time
from database.database import (
    add_user, del_user, full_userbase, present_user,
    present_admin, is_banned, get_fsub_channels, get_settings,
    has_join_request
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _del_after(msg, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def _notify_del(client, msg, delay: int):
    try:
        notif = await msg.reply_text(
            f"⏳ <b>This file will be deleted in {readable_time(delay)}.\nForward it to Saved Messages!</b>"
        )
        await asyncio.sleep(delay)
        await notif.delete()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# /start  (subscribed users)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    uid = message.from_user.id

    # Ban check (subscribed filter handles it but double-guard here)
    if await is_banned(uid):
        await message.reply_text("🚫 You are banned from using this bot.")
        return

    is_owner_or_admin = (uid == OWNER_ID or uid in ADMINS or await present_admin(uid))

    if not await present_user(uid):
        await add_user(uid)

    text = message.text
    if len(text) > 7:
        # File delivery
        try:
            b64 = text.split(" ", 1)[1]
            string = await decode(b64)
            parts = string.split("-")
            if len(parts) == 3:
                start = int(int(parts[1]) / abs(client.db_channel.id))
                end   = int(int(parts[2]) / abs(client.db_channel.id))
                ids = list(range(start, end + 1)) if start <= end else list(range(start, end - 1, -1))
            elif len(parts) == 2:
                ids = [int(int(parts[1]) / abs(client.db_channel.id))]
            else:
                return
        except Exception:
            return

        settings       = await get_settings()
        auto_del       = settings.get("auto_del", True)
        del_timer      = settings.get("del_timer", 120)
        custom_cap     = settings.get("custom_caption")
        protect_content = settings.get("protect_content", False)

        wait_msg = await message.reply("⏳ Please wait...")
        try:
            messages = await get_messages(client, ids)
        except Exception:
            await wait_msg.edit_text("Something went wrong. Try again.")
            return
        await wait_msg.delete()

        last_msg = None
        for idx, msg in enumerate(messages):
            caption = (
                custom_cap.format(
                    previouscaption="" if not msg.caption else msg.caption.html,
                    filename=msg.document.file_name if msg.document else "",
                )
                if custom_cap and msg.document
                else ("" if not msg.caption else msg.caption.html)
            )
            try:
                sent = await msg.copy(
                    chat_id=uid,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                    protect_content=protect_content,
                )
                # Skip auto-delete for owner/admin
                if auto_del and not is_owner_or_admin:
                    asyncio.create_task(_del_after(sent, del_timer))
                if idx == len(messages) - 1:
                    last_msg = sent
                await asyncio.sleep(0.1)
            except FloodWait as e:
                await asyncio.sleep(e.x)

        if auto_del and last_msg and not is_owner_or_admin:
            asyncio.create_task(_notify_del(client, last_msg, del_timer))
        return

    # Normal /start
    settings    = await get_settings()
    start_text  = settings.get("custom_start_msg") or START_MSG

    buttons = [
        [InlineKeyboardButton("❓ Help", callback_data="help"),
         InlineKeyboardButton("ℹ️ About", callback_data="about")],
        [InlineKeyboardButton("❌ Close", callback_data="close")],
    ]
    formatted = start_text.format(
        first=message.from_user.first_name,
        last=message.from_user.last_name or "",
        username="" if not message.from_user.username else "@" + message.from_user.username,
        mention=message.from_user.mention,
        id=uid,
    )
    markup = InlineKeyboardMarkup(buttons)
    if START_PIC:
        await message.reply_photo(photo=START_PIC, caption=formatted, reply_markup=markup)
    else:
        await message.reply_text(text=formatted, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# /start  (NOT subscribed)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("start") & filters.private)
async def not_joined(client: Bot, message: Message):
    if await is_banned(message.from_user.id):
        await message.reply_text("🚫 You are banned from using this bot.")
        return

    channels  = await get_fsub_channels()
    uid_check = message.from_user.id
    is_owner_admin = (uid_check == OWNER_ID or uid_check in ADMINS or await present_admin(uid_check))

    # Collect all channel buttons, then pair them 2 per row
    ch_buttons = []
    for ch in channels:
        ch_id   = ch.get('id')
        ch_type = ch.get('type', 'public')

        if ch_type == 'folder':
            link = ch.get('link') or ""
            if not link:
                continue
            name = ch.get('custom_name') or "Folder"
            ch_buttons.append(InlineKeyboardButton(name, url=link))
            continue

        # Resolve display name: custom_name > Telegram title > ID
        try:
            tg_name = (await client.get_chat(ch_id)).title or str(ch_id)
        except Exception:
            tg_name = str(ch_id)
        name = ch.get('custom_name') or tg_name

        if ch_type == 'request':
            link = ch.get('link') or ""
            if not link:
                continue
            already = (not is_owner_admin) and await has_join_request(uid_check, ch_id)
            label   = f"{name} ✅" if already else name
            ch_buttons.append(InlineKeyboardButton(label, url=link))
        else:
            link = client.fsub_invite_links.get(ch_id, "")
            if link:
                ch_buttons.append(InlineKeyboardButton(name, url=link))

    # Pair buttons 2 per row
    buttons = []
    for i in range(0, len(ch_buttons), 2):
        buttons.append(ch_buttons[i:i+2])

    try:
        deep = message.command[1]
        buttons.append([InlineKeyboardButton("🔄 Reload", url=f"https://t.me/{client.username}?start={deep}")])
    except IndexError:
        pass

    caption = FORCE_MSG.format(
        first=message.from_user.first_name,
        last=message.from_user.last_name or "",
        username="" if not message.from_user.username else "@" + message.from_user.username,
        mention=message.from_user.mention,
        id=message.from_user.id,
    )
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    if FORCE_PIC:
        await message.reply_photo(photo=FORCE_PIC, caption=caption, reply_markup=markup)
    else:
        await message.reply_text(text=caption, reply_markup=markup)


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks (help / about / close)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex("^(help|about|close|home)$"))
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    back = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home"),
                                   InlineKeyboardButton("❌ Close", callback_data="close")]])
    if data == "help":
        await query.message.edit_text(HELP_TXT, reply_markup=back, disable_web_page_preview=True)
    elif data == "about":
        await query.message.edit_text(
            ABOUT_TXT.format(first=query.from_user.first_name),
            reply_markup=back,
            disable_web_page_preview=True,
        )
    elif data == "home":
        home_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Help", callback_data="help"),
             InlineKeyboardButton("ℹ️ About", callback_data="about")],
            [InlineKeyboardButton("❌ Close", callback_data="close")],
        ])
        await query.message.edit_text(
            START_MSG.format(first=query.from_user.first_name, last="", username="", mention="", id=""),
            reply_markup=home_btns,
            disable_web_page_preview=True,
        )
    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("status") & filters.private)
async def status_cmd(client: Bot, message: Message):
    uid = message.from_user.id
    if uid != OWNER_ID and not await present_admin(uid):
        await message.reply_text("❌ Only admins can use this.")
        return

    from datetime import datetime
    up = datetime.now() - client.uptime
    h, rem = divmod(int(up.total_seconds()), 3600)
    m, s   = divmod(rem, 60)

    users    = await full_userbase()
    channels = await get_fsub_channels()
    settings = await get_settings()

    text = (
        f"<b>📊 Bot Status</b>\n\n"
        f"⏱ Uptime: <code>{h}h {m}m {s}s</code>\n"
        f"👥 Users: <code>{len(users)}</code>\n"
        f"📢 FSub Channels: <code>{len(channels)}</code>\n"
        f"🗑 Auto Delete: <code>{'On' if settings.get('auto_del') else 'Off'}</code>\n"
        f"⏳ Delete Timer: <code>{readable_time(settings.get('del_timer', 120))}</code>\n"
        f"📦 Dump Channel: <code>{settings.get('dump_channel') or 'Not set'}</code>"
    )
    await message.reply_text(text)


# ─────────────────────────────────────────────────────────────────────────────
# /broadcast  (owner only)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("bord") & filters.private)
async def broadcast(client: Bot, message: Message):
    uid = message.from_user.id
    if uid != OWNER_ID and uid not in ADMINS and not await present_admin(uid):
        await message.reply_text("❌ Only admins can use this command.")
        return
    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /bord to broadcast it.")
        return

    users = await full_userbase()
    bcast = message.reply_to_message
    total = successful = blocked = deleted = failed = 0

    prog = await message.reply("⏳ Broadcasting...")
    for uid in users:
        try:
            await bcast.copy(uid)
            successful += 1
        except FloodWait as e:
            await asyncio.sleep(e.x)
            try:
                await bcast.copy(uid)
                successful += 1
            except Exception:
                failed += 1
        except UserIsBlocked:
            await del_user(uid)
            blocked += 1
        except InputUserDeactivated:
            await del_user(uid)
            deleted += 1
        except Exception:
            failed += 1
        total += 1

    await prog.edit_text(
        f"<b>📣 Broadcast Complete</b>\n\n"
        f"Total: <code>{total}</code>\n"
        f"✅ Success: <code>{successful}</code>\n"
        f"🚫 Blocked: <code>{blocked}</code>\n"
        f"❌ Deleted: <code>{deleted}</code>\n"
        f"⚠️ Failed: <code>{failed}</code>"
    )
