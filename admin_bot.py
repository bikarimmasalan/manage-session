import asyncio
import os
import re
import sqlite3
from typing import Dict

from telethon import Button, events
from telethon.errors import MessageNotModifiedError

from accounts import ensure_sessions_dir
from config import (
    ADMIN_IDS,
    GROUP_INTERVAL_MINUTES,
    MAX_ACCOUNT_DAYS,
    MAX_GROUPS_PER_ACCOUNT,
    SESSIONS_DIR,
)
from scheduler import is_scheduler_running, start_scheduler, stop_scheduler

PAGE_SIZE = 5
ADMIN_STATE: Dict[int, Dict] = {}


def setup_admin_handlers(bot):
    """Setup all admin bot handlers"""
    
    @bot.on(events.NewMessage(pattern="/start"))
    async def start_handler(event):
        if event.sender_id not in ADMIN_IDS:
            await event.reply("⛔ Access denied.")
            return
        
        await show_main_menu(event)
    
    async def show_main_menu(event):
        """Show main menu"""
        text = (
            "🤖 <b>Telegram Account Manager</b>\n\n"
            "Select an option:"
        )
        buttons = [
            [
                Button.inline("📱 Accounts", data=b"menu:accounts"),
                Button.inline("📊 Statistics", data=b"menu:stats")
            ],
            [
                Button.inline("⚠️ Errors", data=b"menu:errors"),
                Button.inline("⏱ Scheduler", data=b"menu:scheduler")
            ],
            [Button.inline("➕ Add Account", data=b"accounts:add")]
        ]
        await event.respond(text, buttons=buttons, parse_mode="html")
    
    async def show_accounts_page(event, page: int = 1):
        """Show paginated accounts list"""
        from db import get_accounts
        accounts = await get_accounts(active_only=False)
        total = len(accounts)
        
        if total == 0:
            text = "📱 <b>No accounts found</b>\n\nAdd an account to get started."
            buttons = [
                [Button.inline("➕ Add Account", data=b"accounts:add")],
                [Button.inline("⬅️ Back", data=b"menu:back")]
            ]
            await event.edit(text, buttons=buttons, parse_mode="html")
            return
        
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        page_accounts = accounts[start_idx:end_idx]
        
        lines = [f"📱 <b>Accounts</b> (Page {page}/{total_pages})\n"]
        btn_rows = []
        
        for acc in page_accounts:
            acc_id = acc["id"]
            phone = acc["phone"]
            groups = acc["created_groups_count"] or 0
            active = "🟢" if acc["is_active"] else "🔴"
            proxy = "🌐" if acc["proxy_host"] else "🚫"
            
            status_line = f"{active} <code>{phone}</code> | Groups: {groups}/{MAX_GROUPS_PER_ACCOUNT}"
            if acc.get("disabled_reason"):
                status_line += f"\n   ⚠️ {acc['disabled_reason']}"
            lines.append(status_line)
            
            btn_rows.append([
                Button.inline(f"📋 {phone}", data=f"account:view:{acc_id}".encode())
            ])
        
        # Navigation
        nav_buttons = []
        if page > 1:
            nav_buttons.append(Button.inline("◀️ Prev", data=f"menu:accounts:{page-1}".encode()))
        nav_buttons.append(Button.inline(f"📄 {page}/{total_pages}", data=b"none"))
        if page < total_pages:
            nav_buttons.append(Button.inline("Next ▶️", data=f"menu:accounts:{page+1}".encode()))
        
        if nav_buttons:
            btn_rows.append(nav_buttons)
        
        btn_rows.append([
            Button.inline("➕ Add Account", data=b"accounts:add"),
            Button.inline("⬅️ Back", data=b"menu:back")
        ])
        
        await event.edit("\n".join(lines), buttons=btn_rows, parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=b"menu:accounts"))
    async def cb_menu_accounts(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        await show_accounts_page(event, page=1)
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"menu:accounts:(\d+)")))
    async def cb_menu_accounts_page(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"menu:accounts:(\d+)", event.data)
        page = int(m.group(1))
        await show_accounts_page(event, page=page)
    
    async def show_account_details(event, acc_id: int):
        from db import get_account_by_id
        acc = await get_account_by_id(acc_id)
        
        if not acc:
            await event.answer("Account not found", alert=True)
            return
        
        # Build info text
        status = "🟢 Active" if acc["is_active"] else "🔴 Inactive"
        proxy_text = (
            f"{acc['proxy_host']}:{acc['proxy_port']}" if acc.get("proxy_host") else "Not configured"
        )
        groups = acc["created_groups_count"] or 0
        
        info = [
            f"📱 <b>Account Details</b>\n",
            f"📞 Phone: <code>{acc['phone']}</code>",
            f"🏷 Label: {acc['label']}",
            f"⚡ Status: {status}",
            f"📊 Groups: {groups}/{MAX_GROUPS_PER_ACCOUNT}",
            f"🌐 Proxy: <code>{proxy_text}</code>",
            f"📅 Added: {acc['added_at'][:10]}"
        ]
        
        if acc.get("disabled_reason"):
            info.append(f"\n⚠️ <b>Disabled:</b> {acc['disabled_reason']}")
        
        if acc.get("first_activity_at"):
            info.append(f"🕐 First Activity: {acc['first_activity_at'][:10]}")
        if acc.get("last_group_created_at"):
            info.append(f"🕐 Last Group: {acc['last_group_created_at'][:19]}")
        
        buttons = [
            [
                Button.inline(
                    "✅ Enable" if not acc["is_active"] else "❌ Disable",
                    data=f"account:toggle:{acc_id}".encode()
                ),
                Button.inline("🌐 Proxy", data=f"account:proxy:{acc_id}".encode())
            ],
            [
                Button.inline("💾 Download Session", data=f"account:download:{acc_id}".encode()),
                Button.inline("🗑 Delete", data=f"account:delete:{acc_id}".encode())
            ],
            [Button.inline("⬅️ Back", data=b"menu:accounts")]
        ]
        
        await event.edit("\n".join(info), buttons=buttons, parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:view:(\d+)")))
    async def cb_account_view(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:view:(\d+)", event.data)
        acc_id = int(m.group(1))
        await show_account_details(event, acc_id)
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:toggle:(\d+)")))
    async def cb_account_toggle(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:toggle:(\d+)", event.data)
        acc_id = int(m.group(1))
        
        from db import toggle_account_active, get_account_by_id
        updated = await toggle_account_active(acc_id)
        
        if not updated:
            await event.answer("Account not found", alert=True)
            return
        
        status = "enabled" if updated["is_active"] else "disabled"
        await event.answer(f"✅ Account {status}", alert=True)
        
        await show_account_details(event, acc_id)
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:proxy:(\d+)")))
    async def cb_account_proxy(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:proxy:(\d+)", event.data)
        acc_id = int(m.group(1))
        
        ADMIN_STATE[event.sender_id] = {"mode": "setting_proxy", "account_id": acc_id}
        
        text = (
            f"🌐 <b>Proxy Settings</b>\n\n"
            f"Send proxy in one of these formats:\n"
            f"<code>host:port</code>\n"
            f"<code>host:port:username:password</code>\n\n"
            f"Send <code>none</code> to clear proxy."
        )
        await event.reply(text, parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:download:(\d+)")))
    async def cb_account_download(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:download:(\d+)", event.data)
        acc_id = int(m.group(1))
        
        from db import get_account_by_id
        acc = await get_account_by_id(acc_id)
        
        if not acc:
            await event.answer("Account not found", alert=True)
            return
        
        session_path = acc["session_path"]
        if not os.path.isabs(session_path):
            session_path = os.path.join(SESSIONS_DIR, session_path)
        
        if os.path.exists(session_path):
            await event.reply(file=session_path, caption=f"📎 Session file for {acc['phone']}")
            await event.answer("✅ Session file sent")
        else:
            await event.answer("❌ Session file not found", alert=True)
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:delete:(\d+)")))
    async def cb_account_delete(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:delete:(\d+)", event.data)
        acc_id = int(m.group(1))
        
        buttons = [
            [
                Button.inline("✅ Yes, Delete", data=f"account:delete:confirm:{acc_id}".encode()),
                Button.inline("❌ Cancel", data=f"account:view:{acc_id}".encode())
            ]
        ]
        
        await event.edit(
            "⚠️ <b>Confirm Deletion</b>\n\n"
            "Are you sure you want to delete this account?\n"
            "This action cannot be undone!",
            buttons=buttons,
            parse_mode="html"
        )
    
    @bot.on(events.CallbackQuery(pattern=re.compile(br"account:delete:confirm:(\d+)")))
    async def cb_account_delete_confirm(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        m = re.match(br"account:delete:confirm:(\d+)", event.data)
        acc_id = int(m.group(1))
        
        from db import get_account_by_id, delete_account
        from accounts import disconnect_client
        
        acc = await get_account_by_id(acc_id)
        
        if not acc:
            await event.answer("Account not found", alert=True)
            return
        
        # Disconnect client
        await disconnect_client(acc_id)
        
        # Delete session files
        session_path = acc["session_path"]
        if not os.path.isabs(session_path):
            session_path = os.path.join(SESSIONS_DIR, session_path)
        for ext in ["", "-journal"]:
            file_path = session_path + ext
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete from database
        await delete_account(acc_id)
        
        await event.edit(
            f"✅ Account <code>{acc['phone']}</code> deleted successfully",
            parse_mode="html"
        )
        await asyncio.sleep(2)
        await show_accounts_page(event, page=1)
    
    @bot.on(events.CallbackQuery(pattern=b"menu:stats"))
    async def cb_menu_stats(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        from db import get_global_stats
        stats = await get_global_stats()
        
        lines = [
            "📊 <b>Global Statistics</b>\n",
            f"📱 Total Accounts: {stats['total_accounts']}",
            f"🟢 Active: {stats['active_accounts']}",
            f"🔴 Inactive: {stats['total_accounts'] - stats['active_accounts']}",
            f"📂 Total Groups: {stats['total_groups']}\n",
            "<b>Per Account:</b>"
        ]
        
        for acc in stats["accounts"]:
            active = "🟢" if acc["is_active"] else "🔴"
            proxy = "🌐" if acc["proxy_host"] else "🚫"
            groups = acc["created_groups_count"] or 0
            lines.append(
                f"{active} {proxy} <code>{acc['phone']}</code> - {groups}/{MAX_GROUPS_PER_ACCOUNT} groups"
            )
        
        buttons = [[Button.inline("⬅️ Back", data=b"menu:back")]]
        await event.edit("\n".join(lines), buttons=buttons, parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=b"menu:errors"))
    async def cb_menu_errors(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        from db import get_latest_errors
        errors = await get_latest_errors(10)
        
        if not errors:
            text = "✅ <b>No errors logged</b>"
        else:
            lines = ["⚠️ <b>Latest Errors:</b>\n"]
            for err in errors:
                acc_id = err["account_id"] or "N/A"
                context = err["context"]
                created_at = err["created_at"][:19]
                snippet = err["error_text"][:150]
                lines.append(
                    f"[{created_at}] Account {acc_id}\n"
                    f"Context: {context}\n"
                    f"Error: {snippet}\n"
                )
            text = "\n".join(lines)
        
        buttons = [[Button.inline("⬅️ Back", data=b"menu:back")]]
        await event.edit(text, buttons=buttons, parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=b"menu:scheduler"))
    async def cb_menu_scheduler(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        running = is_scheduler_running()
        status = "🟢 Running" if running else "🔴 Stopped"
        
        text = (
            f"⏱ <b>Scheduler Status:</b> {status}\n\n"
            f"<b>Settings:</b>\n"
            f"⏰ Interval: {GROUP_INTERVAL_MINUTES} minutes\n"
            f"📊 Max Groups: {MAX_GROUPS_PER_ACCOUNT} per account\n"
            f"📅 Max Days: {MAX_ACCOUNT_DAYS} days"
        )
        
        buttons = [
            [
                Button.inline("▶️ Start", data=b"scheduler:start"),
                Button.inline("⏹ Stop", data=b"scheduler:stop")
            ],
            [Button.inline("⬅️ Back", data=b"menu:back")]
        ]
        
        try:
            await event.edit(text, buttons=buttons, parse_mode="html")
        except MessageNotModifiedError:
            pass
    
    @bot.on(events.CallbackQuery(pattern=b"scheduler:start"))
    async def cb_scheduler_start(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        start_scheduler()
        await event.answer("✅ Scheduler started", alert=True)
        await cb_menu_scheduler(event)
    
    @bot.on(events.CallbackQuery(pattern=b"scheduler:stop"))
    async def cb_scheduler_stop(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        stop_scheduler()
        await event.answer("⏹ Scheduler stopped", alert=True)
        await cb_menu_scheduler(event)
    
    @bot.on(events.CallbackQuery(pattern=b"accounts:add"))
    async def cb_accounts_add(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        
        ensure_sessions_dir()
        ADMIN_STATE[event.sender_id] = {"mode": "adding_account_wait_file"}
        
        text = (
            "➕ <b>Add New Account</b>\n\n"
            "Send the session file (<code>.session</code>) for this account.\n"
            "The filename will be used as the label."
        )
        await event.edit(text, buttons=[[Button.inline("⬅️ Cancel", data=b"menu:accounts")]], parse_mode="html")
    
    @bot.on(events.CallbackQuery(pattern=b"menu:back"))
    async def cb_menu_back(event):
        if event.sender_id not in ADMIN_IDS:
            await event.answer("Access denied", alert=True)
            return
        await event.delete()
        await start_handler(event)
    
    @bot.on(events.NewMessage)
    async def admin_message_handler(event):
        if event.sender_id not in ADMIN_IDS:
            return
        
        state = ADMIN_STATE.get(event.sender_id)
        text = (event.raw_text or "").strip()
        
        # Adding account - waiting for session file
        if state and state.get("mode") == "adding_account_wait_file":
            if event.document:
                file_name = event.file.name or "session.session"
                if not file_name.endswith(".session"):
                    await event.reply("❌ File must be a .session file")
                    return
                
                ensure_sessions_dir()
                path = os.path.join(SESSIONS_DIR, file_name)
                await event.download_media(file=path)
                
                label = os.path.splitext(file_name)[0]
                phone = label.replace("session_", "+")
                
                from db import add_account
                try:
                    await add_account(phone=phone, session_path=file_name, label=label)
                except sqlite3.IntegrityError:
                    if os.path.exists(path):
                        os.remove(path)
                    await event.reply(
                        "❌ This account already exists. Session upload removed."
                    )
                    return
                except Exception:
                    if os.path.exists(path):
                        os.remove(path)
                    await event.reply("❌ Failed to add account. Please try again.")
                    return
                
                ADMIN_STATE.pop(event.sender_id, None)
                await event.reply(
                    f"✅ <b>Account added successfully</b>\n\n"
                    f"Label: {label}\n"
                    f"Session: {file_name}",
                    parse_mode="html"
                )
            else:
                await event.reply("Please send a .session file")
            return
        
        # Setting proxy
        if state and state.get("mode") == "setting_proxy":
            acc_id = state.get("account_id")
            
            # Clear proxy
            if text.lower() == "none":
                from db import update_proxy
                await update_proxy(acc_id, None, None, None, None)
                ADMIN_STATE.pop(event.sender_id, None)
                await event.reply(f"✅ Proxy cleared for account {acc_id}")
                return
            
            # Parse proxy format
            parts = text.split(":")
            if len(parts) not in (2, 4):
                await event.reply(
                    "❌ Invalid format\n"
                    "Use: <code>host:port</code> or <code>host:port:username:password</code>",
                    parse_mode="html"
                )
                return
            
            host = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                await event.reply("❌ Port must be a number")
                return
            
            username = parts[2] if len(parts) == 4 else None
            password = parts[3] if len(parts) == 4 else None
            
            from db import update_proxy
            await update_proxy(acc_id, host, port, username, password)
            ADMIN_STATE.pop(event.sender_id, None)
            await event.reply(f"✅ Proxy updated for account {acc_id}")
            return
