import asyncio
import pymongo
from config import DB_URI, DB_NAME

dbclient = pymongo.MongoClient(DB_URI)
database = dbclient[DB_NAME]

user_data     = database['users']
admin_data    = database['admins']
banned_data   = database['banned']
fsub_data     = database['fsub_channels']
settings_data = database['bot_settings']
upload_stats  = database['upload_stats']


# ── Users ──────────────────────────────────────────────────────────────────────
async def present_user(user_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, user_data.find_one, {'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    if not await present_user(user_id):
        user_data.insert_one({'_id': user_id})

async def del_user(user_id: int):
    user_data.delete_one({'_id': user_id})

async def full_userbase() -> list:
    return [doc['_id'] for doc in user_data.find()]


# ── Admins ─────────────────────────────────────────────────────────────────────
async def present_admin(admin_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, admin_data.find_one, {'_id': admin_id})
    return bool(found)

async def add_admin(admin_id: int) -> bool:
    """Returns True if already existed."""
    if await present_admin(admin_id):
        return True
    admin_data.insert_one({'_id': admin_id})
    return False

async def del_admin(admin_id: int) -> bool:
    """Returns True if not found (nothing removed)."""
    if not await present_admin(admin_id):
        return True
    admin_data.delete_one({'_id': admin_id})
    return False

async def full_adminbase() -> list:
    return [doc['_id'] for doc in admin_data.find()]


# ── Banned users ───────────────────────────────────────────────────────────────
async def is_banned(user_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, banned_data.find_one, {'_id': user_id})
    return bool(found)

async def ban_user(user_id: int):
    if not await is_banned(user_id):
        banned_data.insert_one({'_id': user_id})

async def unban_user(user_id: int):
    banned_data.delete_one({'_id': user_id})


# ── FSub channels ──────────────────────────────────────────────────────────────
# Each channel stored as:
#   { 'id': int, 'type': 'public' | 'request', 'link': str | None }
#
# public  → bot is admin, membership checked via get_chat_member
# request → private channel with approval; owner sets custom join-request link

def _get_fsub_doc() -> dict:
    doc = fsub_data.find_one({'_id': 'fsub'})
    return doc or {'_id': 'fsub', 'channels': []}

async def get_fsub_channels() -> list:
    """Returns list of channel dicts: [{id, type, link}, ...]"""
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, _get_fsub_doc)
    return doc.get('channels', [])

async def add_fsub_channel(channel_id: int, ch_type: str, link: str = None) -> bool:
    """Returns False if already exists, True on success."""
    channels = await get_fsub_channels()
    if any(ch['id'] == channel_id for ch in channels):
        return False
    channels.append({'id': channel_id, 'type': ch_type, 'link': link})
    fsub_data.update_one({'_id': 'fsub'}, {'$set': {'channels': channels}}, upsert=True)
    return True

async def update_fsub_channel(channel_id: int, ch_type: str, link: str = None):
    """Update type/link of an existing fsub channel."""
    channels = await get_fsub_channels()
    for ch in channels:
        if ch['id'] == channel_id:
            ch['type'] = ch_type
            ch['link'] = link
            break
    fsub_data.update_one({'_id': 'fsub'}, {'$set': {'channels': channels}}, upsert=True)

async def remove_fsub_channel(channel_id: int) -> bool:
    """Returns False if not found."""
    channels = await get_fsub_channels()
    new = [ch for ch in channels if ch['id'] != channel_id]
    if len(new) == len(channels):
        return False
    fsub_data.update_one({'_id': 'fsub'}, {'$set': {'channels': new}}, upsert=True)
    return True


# ── Bot settings ───────────────────────────────────────────────────────────────
def _default_settings() -> dict:
    return {
        '_id': 'settings',
        'auto_del': True,
        'del_timer': 120,
        'dump_channel': None,
        'custom_start_msg': None,
    }

async def get_settings() -> dict:
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, settings_data.find_one, {'_id': 'settings'})
    if not doc:
        defaults = _default_settings()
        settings_data.insert_one(defaults)
        return defaults
    return doc

async def update_setting(key: str, value):
    settings_data.update_one({'_id': 'settings'}, {'$set': {key: value}}, upsert=True)


# ── Join Requests ─────────────────────────────────────────────────────────────
# Stores user IDs who have sent a join request to any request-type fsub channel

join_requests = database['join_requests']

async def has_join_request(user_id: int, channel_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(
        None, join_requests.find_one, {'user_id': user_id, 'channel_id': channel_id}
    )
    return bool(found)

async def save_join_request(user_id: int, channel_id: int):
    if not await has_join_request(user_id, channel_id):
        join_requests.insert_one({'user_id': user_id, 'channel_id': channel_id})

async def remove_join_request(user_id: int, channel_id: int):
    join_requests.delete_one({'user_id': user_id, 'channel_id': channel_id})


# ── Upload / rank stats ────────────────────────────────────────────────────────
async def record_upload(user_id: int, count: int = 1):
    upload_stats.update_one({'_id': user_id}, {'$inc': {'uploads': count}}, upsert=True)

async def get_upload_stats(user_id: int) -> int:
    doc = upload_stats.find_one({'_id': user_id})
    return doc['uploads'] if doc else 0

async def get_leaderboard(limit: int = 10) -> list:
    docs = upload_stats.find().sort('uploads', pymongo.DESCENDING).limit(limit)
    return [(doc['_id'], doc['uploads']) for doc in docs]
