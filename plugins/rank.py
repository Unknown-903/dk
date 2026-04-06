from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import OWNER_ID, ADMINS
from database.database import get_leaderboard, get_upload_stats, present_admin


async def _is_owner_or_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in ADMINS or await present_admin(uid)


@Bot.on_message(filters.command("rank") & filters.private)
async def rank_cmd(client: Bot, message: Message):
    uid = message.from_user.id

    if not await _is_owner_or_admin(uid):
        await message.reply_text("❌ Only admins can use this command.")
        return

    board = await get_leaderboard(limit=10)
    if not board:
        await message.reply_text("📭 No uploads recorded yet.")
        return

    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = ["<b>🏆 Upload Leaderboard</b>\n"]

    for i, (user_id, uploads) in enumerate(board):
        try:
            u    = await client.get_users(user_id)
            name = u.first_name
        except Exception:
            name = str(user_id)
        lines.append(f"{medals[i]} <b>{name}</b> — <code>{uploads}</code> uploads")

    await message.reply_text("\n".join(lines))
