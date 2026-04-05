import asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus

from bot import Bot
from config import OWNER_ID
from database.database import get_fsub_channels, add_fsub_channel, update_fsub_channel, remove_fsub_channel


# ── Helper ────────────────────────────────────────────────────────────────────
async def _bot_is_admin(client, channel_id: int) -> bool:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

def _display_name(ch: dict, fallback: str) -> str:
    """Custom name if set, else Telegram channel title."""
    return ch.get('custom_name') or fallback

def _type_icon(ch_type: str) -> str:
    return {"request": "📨", "private": "🔒", "public": "🌐"}.get(ch_type, "🌐")


# ── mfsub panel builder ───────────────────────────────────────────────────────
async def _mfsub_panel(client) -> tuple:
    channels = await get_fsub_channels()
    if not channels:
        return (
            "📭 <b>Koi FSub channel set nahi hai.</b>\n/fsub se add karo.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="mfsub_close")]])
        )

    lines   = ["<b>📢 FSub Channels:</b>\n"]
    buttons = []
    for ch in channels:
        ch_id   = ch['id']
        ch_type = ch.get('type', 'public')
        try:
            tg_name = (await client.get_chat(ch_id)).title or str(ch_id)
        except Exception:
            tg_name = str(ch_id)

        name = _display_name(ch, tg_name)
        icon = _type_icon(ch_type)
        lines.append(f"{icon} <b>{name}</b> — <code>{ch_id}</code>")
        buttons.append([
            InlineKeyboardButton("✏️ Edit",   callback_data=f"mfsub_edit:{ch_id}"),
            InlineKeyboardButton("🗑 Remove", callback_data=f"mfsub_rm:{ch_id}"),
        ])

    buttons.append([InlineKeyboardButton("❌ Close", callback_data="mfsub_close")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# /fsub — Step 1: choose type
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("fsub") & filters.private & filters.user(OWNER_ID))
async def fsub_start(client: Bot, message: Message):
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Public",  callback_data="fsub_type:public"),
            InlineKeyboardButton("🔒 Private", callback_data="fsub_type:private"),
        ],
        [
            InlineKeyboardButton("📨 Request", callback_data="fsub_type:request"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="fsub_cancel")],
    ])
    await message.reply_text(
        "<b>➕ New FSub Channel</b>\n\n"
        "Channel ka type choose karo:\n\n"
        "🌐 <b>Public</b> — Public channel, bot admin hona chahiye\n"
        "🔒 <b>Private</b> — Private channel, bot admin + invite link\n"
        "📨 <b>Request</b> — Join request collect karta hai (file freely milti hai sirf request bhejne par)",
        reply_markup=markup,
    )


# ─────────────────────────────────────────────────────────────────────────────
# /fsub — Step 2: type chosen → ask ID
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^fsub_type:(request|public|private)$"))
async def fsub_type_chosen(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_type = query.matches[0].group(1)
    icons   = {"request": "📨 Request", "public": "🌐 Public", "private": "🔒 Private"}
    await query.message.edit_text(
        f"<b>{icons[ch_type]} FSub</b>\n\n"
        "Channel ID bhejo (e.g. <code>-1002864509771</code>):\n\n"
        "/cancel to abort."
    )
    await query.answer()

    # Step 2: get channel ID
    try:
        reply = await client.listen(query.message.chat.id, timeout=60)
    except asyncio.TimeoutError:
        await query.message.edit_text("⏰ Timeout. /fsub se dobara try karo.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("❌ Cancelled.")
        return

    try:
        ch_id = int(reply.text.strip())
    except (ValueError, AttributeError):
        await reply.reply_text("❌ Invalid ID. /fsub se dobara try karo.")
        return

    # Validate bot is admin
    if not await _bot_is_admin(client, ch_id):
        await reply.reply_text(
            "❌ <b>Channel nahi mila ya bot admin nahi hai.</b>\n\n"
            "Bot ko admin banao phir /fsub dobara try karo."
        )
        return

    # Step 3: ask custom name
    await reply.reply_text(
        "✏️ Is channel ka <b>custom naam</b> set karna chahte ho?\n\n"
        "Naam bhejo ya <code>skip</code> bhejo Telegram naam rakhne ke liye.\n"
        "/cancel to abort."
    )
    try:
        name_reply = await client.listen(reply.chat.id, timeout=60)
    except asyncio.TimeoutError:
        await reply.reply_text("⏰ Timeout. /fsub se dobara try karo.")
        return

    if name_reply.text and name_reply.text.strip() == "/cancel":
        await name_reply.reply_text("❌ Cancelled.")
        return

    custom_name = None
    if name_reply.text and name_reply.text.strip().lower() != "skip":
        custom_name = name_reply.text.strip()

    # Step 4: for request type → ask join link
    if ch_type == "request":
        await name_reply.reply_text(
            "🔗 Join Request link bhejo\n"
            "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
            "/cancel to abort."
        )
        try:
            link_reply = await client.listen(name_reply.chat.id, timeout=60)
        except asyncio.TimeoutError:
            await name_reply.reply_text("⏰ Timeout. /fsub se dobara try karo.")
            return

        if link_reply.text and link_reply.text.strip() == "/cancel":
            await link_reply.reply_text("❌ Cancelled.")
            return

        custom_link = link_reply.text.strip() if link_reply.text else None
        if not custom_link or not custom_link.startswith("https://t.me/"):
            await link_reply.reply_text(
                "❌ Invalid link. <code>https://t.me/</code> se start hona chahiye.\n"
                "/fsub se dobara try karo."
            )
            return

        added = await add_fsub_channel(ch_id, "request", custom_link, custom_name)
        if not added:
            await link_reply.reply_text(f"⚠️ Channel <code>{ch_id}</code> already added hai.")
            return

        try:
            tg_name = (await client.get_chat(ch_id)).title
        except Exception:
            tg_name = str(ch_id)

        display = custom_name or tg_name
        await link_reply.reply_text(
            f"✅ <b>{display}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: 📨 Request\n"
            f"Link: {custom_link}"
        )

    else:
        # Public / Private
        added = await add_fsub_channel(ch_id, ch_type, None, custom_name)
        if not added:
            await name_reply.reply_text(f"⚠️ Channel <code>{ch_id}</code> already added hai.")
            return

        try:
            chat    = await client.get_chat(ch_id)
            tg_name = chat.title
            link    = chat.invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = link
        except Exception:
            tg_name = str(ch_id)

        display = custom_name or tg_name
        icon    = "🌐 Public" if ch_type == "public" else "🔒 Private"
        await name_reply.reply_text(
            f"✅ <b>{display}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: {icon}"
        )


@Bot.on_callback_query(filters.regex(r"^fsub_cancel$"))
async def fsub_cancel(client: Bot, query: CallbackQuery):
    await query.message.edit_text("❌ Cancelled.")


# ─────────────────────────────────────────────────────────────────────────────
# /mfsub — manage channels
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("mfsub") & filters.private & filters.user(OWNER_ID))
async def mfsub_cmd(client: Bot, message: Message):
    text, markup = await _mfsub_panel(client)
    await message.reply_text(text, reply_markup=markup)


# Remove
@Bot.on_callback_query(filters.regex(r"^mfsub_rm:(-?\d+)$"))
async def mfsub_remove(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    removed = await remove_fsub_channel(ch_id)
    client.fsub_invite_links.pop(ch_id, None)
    await query.answer(f"✅ Removed." if removed else "⚠️ Not found.", show_alert=True)

    text, markup = await _mfsub_panel(client)
    await query.message.edit_text(text, reply_markup=markup)


# Edit — show sub-menu
@Bot.on_callback_query(filters.regex(r"^mfsub_edit:(-?\d+)$"))
async def mfsub_edit(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id    = int(query.matches[0].group(1))
    channels = await get_fsub_channels()
    ch       = next((c for c in channels if c['id'] == ch_id), None)
    if not ch:
        await query.answer("Channel nahi mila.", show_alert=True)
        return

    try:
        tg_name = (await client.get_chat(ch_id)).title or str(ch_id)
    except Exception:
        tg_name = str(ch_id)

    name    = _display_name(ch, tg_name)
    ch_type = ch.get('type', 'public')
    icon    = _type_icon(ch_type)

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Public",  callback_data=f"mfsub_chtype:{ch_id}:public"),
            InlineKeyboardButton("🔒 Private", callback_data=f"mfsub_chtype:{ch_id}:private"),
        ],
        [
            InlineKeyboardButton("📨 Request", callback_data=f"mfsub_chtype:{ch_id}:request"),
        ],
        [InlineKeyboardButton("🔗 Link update karo",    callback_data=f"mfsub_chlink:{ch_id}")],
        [InlineKeyboardButton("✏️ Custom naam badlo",   callback_data=f"mfsub_chname:{ch_id}")],
        [InlineKeyboardButton("⬅️ Back",                callback_data="mfsub_back")],
    ])
    await query.message.edit_text(
        f"<b>✏️ Edit: {name}</b>\n"
        f"ID: <code>{ch_id}</code>\n"
        f"Type: {icon} <b>{ch_type}</b>\n"
        f"Custom naam: <b>{ch.get('custom_name') or 'None'}</b>\n"
        f"Link: <b>{ch.get('link') or 'None'}</b>",
        reply_markup=markup,
    )
    await query.answer()


# Change type
@Bot.on_callback_query(filters.regex(r"^mfsub_chtype:(-?\d+):(request|public|private)$"))
async def mfsub_change_type(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id   = int(query.matches[0].group(1))
    ch_type = query.matches[0].group(2)

    if ch_type == "request":
        await query.message.edit_text(
            "🔗 Join Request link bhejo\n"
            "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
            "/cancel to abort."
        )
        await query.answer()
        try:
            reply = await client.listen(query.message.chat.id, timeout=60)
        except asyncio.TimeoutError:
            await query.message.edit_text("⏰ Timeout. /mfsub se dobara try karo.")
            return

        if reply.text and reply.text.strip() == "/cancel":
            await reply.reply_text("❌ Cancelled.")
            return

        link = reply.text.strip() if reply.text else None
        if not link or not link.startswith("https://t.me/"):
            await reply.reply_text("❌ Invalid link. /mfsub se dobara try karo.")
            return

        await update_fsub_channel(ch_id, ch_type="request", link=link)
        await reply.reply_text("✅ Type → 📨 Request")
    else:
        await update_fsub_channel(ch_id, ch_type=ch_type, link=None)
        try:
            inv_link = (await client.get_chat(ch_id)).invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = inv_link
        except Exception:
            pass
        icon = "🌐 Public" if ch_type == "public" else "🔒 Private"
        await query.message.edit_text(f"✅ Type → {icon}")
        await query.answer()

    text, markup = await _mfsub_panel(client)
    await query.message.reply_text(text, reply_markup=markup)


# Update link only
@Bot.on_callback_query(filters.regex(r"^mfsub_chlink:(-?\d+)$"))
async def mfsub_change_link(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    await query.message.edit_text(
        "🔗 Naya link bhejo (e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n/cancel to abort."
    )
    await query.answer()

    try:
        reply = await client.listen(query.message.chat.id, timeout=60)
    except asyncio.TimeoutError:
        await query.message.edit_text("⏰ Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("❌ Cancelled.")
        return

    link = reply.text.strip() if reply.text else None
    if not link or not link.startswith("https://t.me/"):
        await reply.reply_text("❌ Invalid link.")
        return

    await update_fsub_channel(ch_id, link=link)
    await reply.reply_text(f"✅ Link updated.")

    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# Update custom name
@Bot.on_callback_query(filters.regex(r"^mfsub_chname:(-?\d+)$"))
async def mfsub_change_name(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    await query.message.edit_text(
        "✏️ Naya custom naam bhejo.\n"
        "<code>none</code> bhejo naam hatane ke liye.\n\n"
        "/cancel to abort."
    )
    await query.answer()

    try:
        reply = await client.listen(query.message.chat.id, timeout=60)
    except asyncio.TimeoutError:
        await query.message.edit_text("⏰ Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("❌ Cancelled.")
        return

    val = reply.text.strip() if reply.text else ""
    custom_name = None if val.lower() == "none" else val

    await update_fsub_channel(ch_id, custom_name=custom_name, update_name=True)
    msg = f"✅ Custom naam set: <b>{custom_name}</b>" if custom_name else "✅ Custom naam hata diya."
    await reply.reply_text(msg)

    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# Back to panel
@Bot.on_callback_query(filters.regex(r"^mfsub_back$"))
async def mfsub_back(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return
    text, markup = await _mfsub_panel(client)
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()


# Close
@Bot.on_callback_query(filters.regex(r"^mfsub_close$"))
async def mfsub_close(client: Bot, query: CallbackQuery):
    await query.message.delete()
