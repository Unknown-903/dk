import asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus

from bot import Bot
from config import OWNER_ID
from database.database import get_fsub_channels, add_fsub_channel, update_fsub_channel, remove_fsub_channel


# ── Helper: check bot is admin in channel ─────────────────────────────────────
async def _bot_is_admin(client, channel_id: int) -> bool:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


# ── Build mfsub panel ─────────────────────────────────────────────────────────
async def _mfsub_panel(client) -> tuple[str, InlineKeyboardMarkup]:
    channels = await get_fsub_channels()
    if not channels:
        return (
            "📭 <b>Koi FSub channel set nahi hai.</b>\nUse /fsub to add one.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="mfsub_close")]])
        )

    lines   = ["<b>📢 FSub Channels:</b>\n"]
    buttons = []
    for ch in channels:
        ch_id   = ch['id']
        ch_type = ch.get('type', 'public')
        link    = ch.get('link')
        try:
            chat = await client.get_chat(ch_id)
            name = chat.title
        except Exception:
            name = str(ch_id)

        type_icon = "📨" if ch_type == "request" else ("🔒" if ch_type == "private" else "🌐")
        lines.append(f"{type_icon} <b>{name}</b> — <code>{ch_id}</code> ({ch_type})")

        row = [
            InlineKeyboardButton(f"✏️ Edit", callback_data=f"mfsub_edit:{ch_id}"),
            InlineKeyboardButton(f"🗑 Remove", callback_data=f"mfsub_rm:{ch_id}"),
        ]
        buttons.append(row)

    buttons.append([InlineKeyboardButton("❌ Close", callback_data="mfsub_close")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ─────────────────────────────────────────────────────────────────────────────
# /fsub — add new fsub channel (step-by-step)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("fsub") & filters.private & filters.user(OWNER_ID))
async def fsub_start(client: Bot, message: Message):
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📨 Request", callback_data="fsub_type:request"),
        ],
        [
            InlineKeyboardButton("🌐 Public",  callback_data="fsub_type:public"),
            InlineKeyboardButton("🔒 Private", callback_data="fsub_type:private"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="fsub_cancel")],
    ])
    await message.reply_text(
        "<b>➕ New FSub Channel</b>\n\n"
        "Channel ka type choose karo:\n\n"
        "📨 <b>Request</b> — Join request collect karta hai, file access freely milti hai\n"
        "🌐 <b>Public</b> — Public channel, bot admin hona chahiye\n"
        "🔒 <b>Private</b> — Private channel, bot admin hona chahiye, invite link se join",
        reply_markup=markup,
    )


@Bot.on_callback_query(filters.regex(r"^fsub_type:(request|public|private)$"))
async def fsub_type_chosen(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_type = query.matches[0].group(1)
    icons = {'request': '📨 Request', 'public': '🌐 Public', 'private': '🔒 Private'}
    await query.message.edit_text(
        f"<b>{icons.get(ch_type, ch_type)} FSub</b>\n\n"
        "Ab channel ID bhejo (e.g. <code>-1002864509771</code>):\n\n"
        "Send /cancel to abort."
    )
    await query.answer()

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
            "Pehle bot ko admin banao, phir /fsub dobara try karo."
        )
        return

    # For request type → ask for custom join link
    if ch_type == "request":
        await reply.reply_text(
            "🔗 Ab <b>Join Request link</b> bhejo\n"
            "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
            "Send /cancel to abort."
        )
        try:
            link_reply = await client.listen(reply.chat.id, timeout=60)
        except asyncio.TimeoutError:
            await reply.reply_text("⏰ Timeout. /fsub se dobara try karo.")
            return

        if link_reply.text and link_reply.text.strip() == "/cancel":
            await link_reply.reply_text("❌ Cancelled.")
            return

        custom_link = link_reply.text.strip() if link_reply.text else None
        if not custom_link or not custom_link.startswith("https://t.me/"):
            await link_reply.reply_text(
                "❌ Invalid link. Link <code>https://t.me/</code> se start hona chahiye.\n"
                "/fsub se dobara try karo."
            )
            return

        added = await add_fsub_channel(ch_id, "request", custom_link)
        if not added:
            await link_reply.reply_text(f"⚠️ Channel <code>{ch_id}</code> already added hai.")
            return

        try:
            chat = await client.get_chat(ch_id)
            name = chat.title
        except Exception:
            name = str(ch_id)

        await link_reply.reply_text(
            f"✅ <b>{name}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: 🔒 Request\n"
            f"Link: {custom_link}"
        )

    else:
        # Public or Private type — both need bot as admin
        added = await add_fsub_channel(ch_id, ch_type, None)
        if not added:
            await reply.reply_text(f"⚠️ Channel <code>{ch_id}</code> already added hai.")
            return

        # Cache invite link
        try:
            chat = await client.get_chat(ch_id)
            name = chat.title
            link = chat.invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = link
        except Exception:
            name = str(ch_id)

        icon = "🌐 Public" if ch_type == "public" else "🔒 Private"
        await reply.reply_text(
            f"✅ <b>{name}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: {icon}"
        )


@Bot.on_callback_query(filters.regex(r"^fsub_cancel$"))
async def fsub_cancel(client: Bot, query: CallbackQuery):
    await query.message.edit_text("❌ Cancelled.")


# ─────────────────────────────────────────────────────────────────────────────
# /mfsub — manage existing fsub channels
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("mfsub") & filters.private & filters.user(OWNER_ID))
async def mfsub_cmd(client: Bot, message: Message):
    text, markup = await _mfsub_panel(client)
    await message.reply_text(text, reply_markup=markup)


# Remove channel
@Bot.on_callback_query(filters.regex(r"^mfsub_rm:(-?\d+)$"))
async def mfsub_remove(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    removed = await remove_fsub_channel(ch_id)
    client.fsub_invite_links.pop(ch_id, None)

    if removed:
        await query.answer(f"✅ Channel {ch_id} remove ho gaya.", show_alert=True)
    else:
        await query.answer("⚠️ Channel list mein nahi mila.", show_alert=True)

    text, markup = await _mfsub_panel(client)
    await query.message.edit_text(text, reply_markup=markup)


# Edit channel — show sub-menu
@Bot.on_callback_query(filters.regex(r"^mfsub_edit:(-?\d+)$"))
async def mfsub_edit(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))

    channels = await get_fsub_channels()
    ch = next((c for c in channels if c['id'] == ch_id), None)
    if not ch:
        await query.answer("Channel nahi mila.", show_alert=True)
        return

    try:
        chat = await client.get_chat(ch_id)
        name = chat.title
    except Exception:
        name = str(ch_id)

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📨 Request", callback_data=f"mfsub_chtype:{ch_id}:request"),
            InlineKeyboardButton("🌐 Public",  callback_data=f"mfsub_chtype:{ch_id}:public"),
            InlineKeyboardButton("🔒 Private", callback_data=f"mfsub_chtype:{ch_id}:private"),
        ],
        [InlineKeyboardButton("🔗 Link update karo",      callback_data=f"mfsub_chlink:{ch_id}")],
        [InlineKeyboardButton("⬅️ Back",                  callback_data="mfsub_back")],
    ])
    await query.message.edit_text(
        f"<b>✏️ Edit: {name}</b>\n"
        f"ID: <code>{ch_id}</code>\n"
        f"Current type: <b>{ch.get('type', 'public')}</b>\n"
        f"Current link: <b>{ch.get('link') or 'None'}</b>",
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
        # Need a link
        await query.message.edit_text(
            "🔗 Join Request link bhejo\n"
            "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
            "Send /cancel to abort."
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

        await update_fsub_channel(ch_id, "request", link)
        await reply.reply_text(f"✅ Type → 🔒 Request\nLink: {link}")
    else:
        await update_fsub_channel(ch_id, ch_type, None)
        # Cache invite link for public/private
        try:
            link = (await client.get_chat(ch_id)).invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = link
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
        "🔗 Naya link bhejo\n"
        "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
        "Send /cancel to abort."
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
        await reply.reply_text("❌ Invalid link.")
        return

    channels = await get_fsub_channels()
    ch = next((c for c in channels if c['id'] == ch_id), None)
    ch_type = ch.get('type', 'public') if ch else 'public'
    await update_fsub_channel(ch_id, ch_type, link)
    await reply.reply_text(f"✅ Link updated: {link}")

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


# Close panel
@Bot.on_callback_query(filters.regex(r"^mfsub_close$"))
async def mfsub_close(client: Bot, query: CallbackQuery):
    await query.message.delete()
