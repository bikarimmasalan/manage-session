
import asyncio
import logging
from telethon import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)


async def main():
    """Main application entry point"""
    # Initialize database
    from db import init_db
    await init_db()
    print("✅ Database initialized")
    
    # Create admin bot
    bot = TelegramClient("admin_bot", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    print("✅ Admin bot started")
    
    # Setup admin handlers
    from admin_bot import setup_admin_handlers
    setup_admin_handlers(bot)
    print("✅ Admin handlers registered")
    
    # Start scheduler in background
    from scheduler import run_scheduler
    asyncio.create_task(run_scheduler(bot))
    print("✅ Scheduler started")
    
    # Start forwarding for active accounts
    from db import get_accounts
    from accounts import get_or_create_client, start_forwarding
    
    accounts = await get_accounts(active_only=True)
    for acc in accounts:
        try:
            client = await get_or_create_client(acc)
            await start_forwarding(acc["id"], client)
            print(f"✅ Forwarding enabled for account {acc['id']} ({acc['phone']})")
        except Exception as e:
            print(f"❌ Failed to start account {acc['id']}: {e}")
    
    print("\n🚀 System is ready!")
    print(f"📊 Active accounts: {len(accounts)}")
    print(f"👥 Admin IDs: {', '.join(map(str, ADMIN_IDS))}")
    print("\nPress Ctrl+C to stop...\n")
    
    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Shutting down...")
        from accounts import disconnect_all_clients
        asyncio.run(disconnect_all_clients())
        print("✅ Cleanup complete")