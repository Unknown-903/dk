from pyrogram import filters
from pyrogram.types import ChatJoinRequest

from bot import Bot
from database.database import save_join_request, get_fsub_channels


@Bot.on_chat_join_request()
async def handle_join_request(client: Bot, request: ChatJoinRequest):
    """
    Jab bhi koi user kisi request-type fsub channel mein join request bheje,
    uski user_id aur channel_id DB mein save ho jaayegi.
    """
    user_id    = request.from_user.id
    channel_id = request.chat.id

    # Sirf request-type fsub channels ke liye save karo
    channels = await get_fsub_channels()
    for ch in channels:
        if ch['id'] == channel_id and ch.get('type') == 'request':
            await save_join_request(user_id, channel_id)
            break
