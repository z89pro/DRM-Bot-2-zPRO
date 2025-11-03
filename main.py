import os
from pyrogram import Client as AFK, idle
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram import enums
from pyrogram.types import ChatMember
import asyncio
import logging
import tgcrypto
from pyromod import listen
import logging
from tglogging import TelegramLogHandler

# Load environment variables from .env file if it exists
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Config 
class Config(object):
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    DOWNLOAD_LOCATION = os.environ.get("DOWNLOAD_LOCATION", "./DOWNLOADS")
    SESSIONS = "./SESSIONS"

    AUTH_USERS = os.environ.get('AUTH_USERS').split(',')
    for i in range(len(AUTH_USERS)):
        AUTH_USERS[i] = int(AUTH_USERS[i])

    GROUPS = os.environ.get('GROUPS', '').split(',') if os.environ.get('GROUPS') else []
    for i in range(len(GROUPS)):
        if GROUPS[i]:  # Only convert non-empty strings
            GROUPS[i] = int(GROUPS[i])

    LOG_CH = int(os.environ.get("LOG_CH")) if os.environ.get("LOG_CH") else None
    TARGET_CHAT = None  # Will be set by /set_target command
    CLASSPLUS_EMAIL = None  # Will be set by /login_classplus command
    CLASSPLUS_PASSWORD = None  # Will be set by /login_classplus command

# TelegramLogHandler is a custom handler which is inherited from an existing handler. ie, StreamHandler.
handlers = [logging.StreamHandler()]

# Only add TelegramLogHandler if LOG_CH is provided
if Config.LOG_CH:
    handlers.append(TelegramLogHandler(
        token=Config.BOT_TOKEN, 
        log_chat_id=Config.LOG_CH, 
        update_interval=2, 
        minimum_lines=1, 
        pending_logs=200000))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=handlers
)

LOGGER = logging.getLogger(__name__)
LOGGER.info("live log streaming to telegram.")


# Store
class Store(object):
    CPTOKEN = "eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0"
    SPROUT_URL = "https://discuss.oliveboard.in/"
    ADDA_TOKEN = ""
    THUMB_URL = "https://telegra.ph/file/84870d6d89b893e59c5f0.jpg"

# Format
class Msg(object):
    START_MSG = "**/pro**"

    TXT_MSG = "Hey <b>{user},"\
        "\n\n`I'm Multi-Talented Robot. I Can Download Many Type of Links.`"\
            "\n\nSend a TXT or HTML file :-</b>"

    ERROR_MSG = "<b>DL Failed ({no_of_files}) :-</b> "\
        "\n\n<b>Name: </b>{file_name},\n<b>Link:</b> `{file_link}`\n\n<b>Error:</b> {error}"

    SHOW_MSG = "<b>Downloading :- "\
        "\n`{file_name}`\n\nLink :- `{file_link}`</b>"

    CMD_MSG_1 = "`{txt}`\n\n**Total Links in File are :-** {no_of_links}\n\n**Send any Index From `[ 1 - {no_of_links} ]` :-**"
    CMD_MSG_2 = "<b>Uploading :- </b> `{file_name}`"
    RESTART_MSG = "✅ HI Bhai log\n✅ PATH CLEARED"

# Prefixes
prefixes = ["/", "~", "?", "!", "."]

# Client
plugins = dict(root="plugins")
if __name__ == "__main__":
    if not os.path.isdir(Config.DOWNLOAD_LOCATION):
        os.makedirs(Config.DOWNLOAD_LOCATION)
    if not os.path.isdir(Config.SESSIONS):
        os.makedirs(Config.SESSIONS)

    PRO = AFK(
        "AFK-DL",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        sleep_threshold=120,
        plugins=plugins,
        workdir= f"{Config.SESSIONS}/",
        workers= 2,
    )

    chat_id = []
    for i, j in zip(Config.GROUPS, Config.AUTH_USERS):
        chat_id.append(i)
        chat_id.append(j)
    
    
    async def main():
        await PRO.start()
        
        # Initialize production components
        try:
            from database.database import db_manager
            from core.download_manager import download_manager
            
            # Connect to database
            await db_manager.connect()
            LOGGER.info("Database connected successfully")
            
            # Start download manager
            await download_manager.start()
            LOGGER.info("Download manager started successfully")
            
        except Exception as e:
            LOGGER.error(f"Error initializing production components: {e}")
            # Continue without production features if they fail
        
        bot_info = await PRO.get_me()
        LOGGER.info(f"<--- @{bot_info.username} Started --->")
        
        for i in chat_id:
            try:
                await PRO.send_message(chat_id=i, text="**🚀 Production Bot Started! Use /pro_enhanced for enhanced features**")
            except Exception as d:
                print(d)
                continue
        
        # Start background tasks
        asyncio.create_task(background_cleanup_task())
        asyncio.create_task(system_monitoring_task())
        
        await idle()
        
        # Cleanup on shutdown
        try:
            await download_manager.stop()
            await db_manager.disconnect()
            LOGGER.info("Production components shut down successfully")
        except Exception as e:
            LOGGER.error(f"Error during shutdown: {e}")

    async def background_cleanup_task():
        """Background task for periodic cleanup"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Import here to avoid circular imports
                from database.database import db_manager
                from core.download_manager import download_manager
                
                # Clean up old files
                await download_manager.cleanup_old_files(max_age_hours=24)
                
                # Clean up old database records
                await db_manager.cleanup_old_jobs(days=7)
                await db_manager.cleanup_old_history(days=30)
                await db_manager.cleanup_old_stats(days=7)
                
                LOGGER.info("Background cleanup completed")
                
            except Exception as e:
                LOGGER.error(f"Error in background cleanup: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retry
    
    async def system_monitoring_task():
        """Background task for system monitoring"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # Import here to avoid circular imports
                from database.database import db_manager
                from database.models import SystemStats
                from core.download_manager import download_manager
                
                # Get system status
                system_status = await download_manager.get_system_status()
                resources = system_status['system_resources']
                
                # Create system stats record
                stats = SystemStats(
                    active_downloads=system_status['active_downloads'],
                    queued_downloads=system_status['queue_size'],
                    disk_usage_gb=resources.get('disk_usage_gb', 0),
                    memory_usage_mb=resources.get('memory_usage_mb', 0),
                    cpu_usage_percent=resources.get('cpu_usage_percent', 0)
                )
                
                # Save to database
                await db_manager.save_system_stats(stats)
                
                # Log warnings for high resource usage
                if resources.get('memory_percent', 0) > 85:
                    LOGGER.warning(f"High memory usage: {resources['memory_percent']:.1f}%")
                
                if resources.get('disk_percent', 0) > 90:
                    LOGGER.warning(f"High disk usage: {resources['disk_percent']:.1f}%")
                
            except Exception as e:
                LOGGER.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry

    asyncio.get_event_loop().run_until_complete(main())
    LOGGER.info(f"<---Bot Stopped--->")
