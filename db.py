import aiosqlite
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import DB_PATH


async def init_db():
    """Initialize database tables"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Accounts table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            label TEXT,
            session_path TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_groups_count INTEGER DEFAULT 0,
            first_activity_at TEXT,
            last_group_created_at TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            proxy_host TEXT,
            proxy_port INTEGER,
            proxy_username TEXT,
            proxy_password TEXT,
            disabled_reason TEXT
        )
        """)
        
        # Groups table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            messages_sent INTEGER DEFAULT 0,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        )
        """)
        
        # Errors table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            context TEXT NOT NULL,
            error_text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE SET NULL
        )
        """)
        
        await db.commit()


async def add_account(phone: str, session_path: str, label: str = None) -> int:
    """Add a new account"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO accounts (phone, session_path, label, is_active)
               VALUES (?, ?, ?, 1)""",
            (phone, session_path, label or phone)
        )
        await db.commit()
        return cursor.lastrowid


async def get_accounts(active_only: bool = False) -> List[Dict[str, Any]]:
    """Get all accounts"""
    query = "SELECT * FROM accounts"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id"
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_account_by_id(account_id: int) -> Optional[Dict[str, Any]]:
    """Get account by ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_account_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """Get account by phone"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE phone = ?", (phone,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def toggle_account_active(account_id: int) -> Optional[Dict[str, Any]]:
    """Toggle account active status"""
    account = await get_account_by_id(account_id)
    if not account:
        return None
    
    new_state = 0 if account["is_active"] else 1
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET is_active = ? WHERE id = ?",
            (new_state, account_id)
        )
        await db.commit()
    
    account["is_active"] = new_state
    return account


async def disable_account(account_id: int, reason: str):
    """Disable account with reason"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE accounts 
               SET is_active = 0, disabled_reason = ? 
               WHERE id = ?""",
            (reason, account_id)
        )
        await db.commit()


async def delete_account(account_id: int) -> bool:
    """Delete account from database"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM accounts WHERE id = ?", (account_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_proxy(
    account_id: int,
    host: Optional[str],
    port: Optional[int],
    username: Optional[str],
    password: Optional[str]
):
    """Update account proxy settings"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE accounts
               SET proxy_host = ?, proxy_port = ?, 
                   proxy_username = ?, proxy_password = ?
               WHERE id = ?""",
            (host, port, username, password, account_id)
        )
        await db.commit()


async def create_group_record(
    account_id: int, chat_id: str, title: str
) -> int:
    """Create a group record"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO groups (account_id, chat_id, title, created_at)
               VALUES (?, ?, ?, ?)""",
            (account_id, str(chat_id), title, datetime.utcnow().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def update_group_messages(group_id: int, count: int):
    """Update messages sent count for a group"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE groups SET messages_sent = ? WHERE id = ?",
            (count, group_id)
        )
        await db.commit()


async def increment_account_groups(account_id: int):
    """Increment account's created groups count"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE accounts
               SET created_groups_count = created_groups_count + 1
               WHERE id = ?""",
            (account_id,)
        )
        await db.commit()


async def update_account_activity(
    account_id: int,
    first_activity: Optional[datetime],
    last_group: datetime
):
    """Update account activity timestamps"""
    async with aiosqlite.connect(DB_PATH) as db:
        if first_activity:
            await db.execute(
                """UPDATE accounts
                   SET first_activity_at = ?, last_group_created_at = ?
                   WHERE id = ?""",
                (first_activity.isoformat(), last_group.isoformat(), account_id)
            )
        else:
            await db.execute(
                """UPDATE accounts
                   SET last_group_created_at = ?
                   WHERE id = ?""",
                (last_group.isoformat(), account_id)
            )
        await db.commit()


async def log_error(context: str, error_text: str, account_id: Optional[int] = None):
    """Log an error to database"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO errors (account_id, context, error_text, created_at)
               VALUES (?, ?, ?, ?)""",
            (account_id, context, error_text[:2000], datetime.utcnow().isoformat())
        )
        await db.commit()


async def get_latest_errors(limit: int = 10) -> List[Dict[str, Any]]:
    """Get latest errors"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM errors ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_global_stats() -> Dict[str, Any]:
    """Get global statistics"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM accounts")
        total_accounts = (await cursor.fetchone())["cnt"]
        
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM accounts WHERE is_active = 1"
        )
        active_accounts = (await cursor.fetchone())["cnt"]
        
        cursor = await db.execute(
            "SELECT SUM(created_groups_count) as total FROM accounts"
        )
        row = await cursor.fetchone()
        total_groups = row["total"] if row["total"] else 0
        
        cursor = await db.execute(
            """SELECT id, phone, label, created_groups_count, 
                      is_active, proxy_host, disabled_reason
               FROM accounts ORDER BY id"""
        )
        accounts = [dict(row) for row in await cursor.fetchall()]
        
        return {
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "total_groups": total_groups,
            "accounts": accounts
        }
