import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import OWNER_ID, CHANNEL_ID, ADMINS
from database.database import present_admin, get_settings, record_upload
from helper_func import encode, get_message_id


# ─────────────────────────────────────────────────────────────────────────────
# Private message (admin sends file → generate link)
# ─────────────────────────────────────────────────────────────────────────────
IGNORED_CMDS = ["start", "users", "bord", "batch", "genlink",
                "status", "fsub", "sf", "chnge", "add", "rm", "admins",
                "ban", "unban", "rank", "modify"]

@Bot.on_message(filters.private & ~filters.command(IGNORED_CMDS))
async def channel_post(client: Bot, message: Message):
    uid      = message.from_user.id
    is_admin = await present_admin(uid) or uid == OWNER_ID or uid in ADMINS

    if not is_admin:
        return

    wait = await message.reply_text("⏳ Please wait...")
    try:
        post_msg = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.x)
        post_msg = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except Exception as e:
        await wait.edit_text(f"❌ Error: {e}")
        return

    converted_id  = post_msg.id * abs(client.db_channel.id)
    base64_string = await encode(f"get-{converted_id}")
    link          = f"https://t.me/{client.username}?start={base64_string}"
    share_url     = f"https://telegram.me/share/url?url={link}"

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=share_url)]])
    await wait.edit_text(f"<b>✅ Link Generated</b>\n\n{link}", reply_markup=markup, disable_web_page_preview=True)

    # Stats
    await record_upload(uid)

    # Dump channel mirror
    settings = await get_settings()
    dump_ch  = settings.get("dump_channel")
    if dump_ch:
        try:
            await message.copy(chat_id=dump_ch, disable_notification=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Channel post (auto-add share button)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.channel & filters.incoming & filters.chat(CHANNEL_ID))
async def new_post(client: Client, message: Message):
    converted_id  = message.id * abs(client.db_channel.id)
    base64_string = await encode(f"get-{converted_id}")
    link          = f"https://t.me/{client.username}?start={base64_string}"
    share_url     = f"https://telegram.me/share/url?url={link}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=share_url)]])
    try:
        await message.edit_reply_markup(markup)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# /batch – generate one link for a range of messages
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.command("batch"))
async def batch_cmd(client: Bot, message: Message):
    uid      = message.from_user.id
    is_admin = await present_admin(uid) or uid == OWNER_ID or uid in ADMINS
    if not is_admin:
        return

    async def ask(prompt):
        try:
            reply = await client.ask(message.from_user.id, prompt,
                                     filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                                     timeout=60)
            return reply
        except Exception:
            return None

    while True:
        first_msg = await ask("📩 Forward the <b>first</b> message from DB channel (or send its link):")
        if not first_msg:
            return
        f_id = await get_message_id(client, first_msg)
        if f_id:
            break
        await first_msg.reply("❌ Not from DB channel. Try again.")

    while True:
        last_msg = await ask("📩 Forward the <b>last</b> message from DB channel (or send its link):")
        if not last_msg:
            return
        l_id = await get_message_id(client, last_msg)
        if l_id:
            break
        await last_msg.reply("❌ Not from DB channel. Try again.")

    ch_abs = abs(client.db_channel.id)
    string = f"get-{f_id * ch_abs}-{l_id * ch_abs}"
    b64    = await encode(string)
    link   = f"https://t.me/{client.username}?start={b64}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=f"https://telegram.me/share/url?url={link}")]])
    await last_msg.reply_text(f"<b>✅ Batch Link</b>\n\n{link}", reply_markup=markup)
    await record_upload(uid)


# ─────────────────────────────────────────────────────────────────────────────
# /genlink – generate link for a single message
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.command("genlink"))
async def genlink_cmd(client: Bot, message: Message):
    uid      = message.from_user.id
    is_admin = await present_admin(uid) or uid == OWNER_ID or uid in ADMINS
    if not is_admin:
        return

    try:
        msg = await client.ask(
            message.from_user.id,
            "📩 Forward a message from DB channel or send its link:",
            filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
            timeout=60,
        )
    except Exception:
        return

    msg_id = await get_message_id(client, msg)
    if not msg_id:
        await msg.reply("❌ Not from DB channel.")
        return

    b64    = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
    link   = f"https://t.me/{client.username}?start={b64}"
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Share Link", url=f"https://telegram.me/share/url?url={link}")]])
    await msg.reply_text(f"<b>✅ Link</b>\n\n{link}", reply_markup=markup)
