import asyncio
import logging
from datetime import datetime, timedelta

from telethon import functions
from telethon.errors import ChannelsTooMuchError, FloodWaitError

from config import GROUP_INTERVAL_MINUTES, MAX_ACCOUNT_DAYS, MAX_GROUPS_PER_ACCOUNT, ADMIN_IDS

logger = logging.getLogger(__name__)

# Scheduler control
SCHEDULER_RUNNING = True


def start_scheduler():
    """Start the scheduler"""
    global SCHEDULER_RUNNING
    SCHEDULER_RUNNING = True


def stop_scheduler():
    """Stop the scheduler"""
    global SCHEDULER_RUNNING
    SCHEDULER_RUNNING = False


def is_scheduler_running() -> bool:
    """Check if scheduler is running"""
    return SCHEDULER_RUNNING


async def run_scheduler(bot_client):
    """Main scheduler loop"""
    logger.info("📅 Scheduler started")
    
    while True:
        try:
            if not SCHEDULER_RUNNING:
                await asyncio.sleep(5)
                continue
            
            # Get active accounts
            from db import disable_account, get_accounts, log_error
            accounts = await get_accounts(active_only=True)
            now = datetime.utcnow()
            
            for index, acc in enumerate(accounts, start=1):
                account_id = acc["id"]
                created_groups = acc["created_groups_count"] or 0
                
                # Check if account reached max groups
                if created_groups >= MAX_GROUPS_PER_ACCOUNT:
                    logger.info(f"[Account {account_id}] Reached max groups ({MAX_GROUPS_PER_ACCOUNT})")
                    continue
                
                # Parse timestamps
                first_activity = (
                    datetime.fromisoformat(acc["first_activity_at"])
                    if acc.get("first_activity_at") else None
                )
                last_group = (
                    datetime.fromisoformat(acc["last_group_created_at"])
                    if acc.get("last_group_created_at") else None
                )
                
                # Check 10 days limit
                if first_activity:
                    if now - first_activity > timedelta(days=MAX_ACCOUNT_DAYS):
                        logger.info(f"[Account {account_id}] Exceeded max days ({MAX_ACCOUNT_DAYS})")
                        await disable_account(account_id, "Exceeded maximum active days")
                        continue
                
                # Check 30 minutes interval
                if last_group:
                    if now - last_group < timedelta(minutes=GROUP_INTERVAL_MINUTES):
                        continue
                
                # Create group
                try:
                    await create_group_for_account(acc, index, now, bot_client)
                except ChannelsTooMuchError as e:
                    # Disable account - too many channels/groups
                    logger.warning(f"[Account {account_id}] Too many channels - disabling")
                    await disable_account(
                        account_id,
                        "Exceeded Telegram limit for channels/groups"
                    )
                    if ADMIN_IDS:
                        await bot_client.send_message(
                            ADMIN_IDS[0],
                            f"⚠️ Account {account_id} ({acc['phone']}) disabled\n"
                            f"Reason: Too many channels/groups joined"
                        )
                    else:
                        logger.warning("No ADMIN_IDS configured to notify about disabled account.")
                except FloodWaitError as e:
                    logger.warning(f"[Account {account_id}] FloodWait: {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.exception(f"[Account {account_id}] Error creating group")
                    await log_error(
                        context="scheduler_create_group",
                        error_text=str(e),
                        account_id=account_id
                    )
            
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            logger.exception("Scheduler main loop error")
            await log_error(context="scheduler_main_loop", error_text=str(e))
            await asyncio.sleep(10)


async def create_group_for_account(acc: dict, index: int, now: datetime, bot_client):
    """Create a group for an account"""
    account_id = acc["id"]
    created_groups = acc["created_groups_count"] or 0
    
    # Get or create client
    from accounts import get_or_create_client
    client = await get_or_create_client(acc)
    
    # Generate group title
    group_number = created_groups + 1
    date_str = now.strftime("%Y-%m-%d")
    title = f"ACC{index:02d} • G{group_number:03d} • {date_str}"
    
    # Create supergroup (megagroup)
    result = await client(
        functions.channels.CreateChannelRequest(
            title=title,
            about="Auto-created group",
            megagroup=True
        )
    )
    
    channel = result.chats[0]
    chat_id = channel.id
    
    # Save to database
    from db import (
        create_group_record,
        increment_account_groups,
        update_account_activity,
        update_group_messages
    )
    
    group_db_id = await create_group_record(
        account_id=account_id,
        chat_id=str(chat_id),
        title=title
    )
    
    # Generate and send messages
    messages = generate_datetime_messages(now)
    sent_count = 0
    
    for msg in messages:
        await client.send_message(entity=channel, message=msg)
        sent_count += 1
        await asyncio.sleep(1)
    
    # Update database
    await update_group_messages(group_db_id, sent_count)
    await increment_account_groups(account_id)
    
    first_activity = (
        datetime.fromisoformat(acc["first_activity_at"])
        if acc.get("first_activity_at") else now
    )
    await update_account_activity(
        account_id=account_id,
        first_activity=first_activity,
        last_group=now
    )
    
    logger.info(
        f"[Account {account_id}] Created group '{title}' "
        f"(#{group_number}/{MAX_GROUPS_PER_ACCOUNT}), sent {sent_count} messages"
    )


def generate_datetime_messages(dt: datetime) -> list:
    """Generate 10 datetime-based messages"""
    year = dt.year
    month = dt.month
    day = dt.day
    weekday = dt.strftime("%A")
    hour = dt.hour
    minute = dt.minute
    second = dt.second
    iso = dt.isoformat()
    unix_ts = int(dt.timestamp())
    summary = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    return [
        f"Year: {year}",
        f"Month: {month} ({dt.strftime('%B')})",
        f"Day: {day}",
        f"Weekday: {weekday}",
        f"Hour: {hour}",
        f"Minute: {minute}",
        f"Second: {second}",
        f"ISO: {iso}",
        f"Unix: {unix_ts}",
        f"Summary: {summary}"
    ]
