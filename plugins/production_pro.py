"""
Production-ready /pro command with enhanced features
"""
import os
import uuid
import asyncio
import logging
from datetime import datetime
from pyrogram import filters, Client as AFK
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from main import LOGGER as LOGS, prefixes, Config, Msg
from handlers.tg import TgClient, TgHandler
from handlers.uploader import Upload_to_Tg

# Import production components
from database.database import db_manager
from database.models import User, DownloadJob, DownloadStatus
from core.download_manager import download_manager, DownloadProgress
from core.security import require_auth, secure_input, security_manager

logger = logging.getLogger(__name__)


@AFK.on_message(
    (filters.chat(Config.GROUPS) | filters.chat(Config.AUTH_USERS)) &
    filters.incoming & filters.command("pro_enhanced", prefixes=prefixes)
)
@require_auth
@secure_input(max_length=2000)
async def enhanced_pro_command(bot: AFK, m: Message):
    """Enhanced /pro command with production features"""
    try:
        # Initialize database connection
        await db_manager.connect()
        
        # Get or create user
        user = await db_manager.get_or_create_user(
            user_id=m.from_user.id,
            username=m.from_user.username,
            first_name=m.from_user.first_name,
            last_name=m.from_user.last_name
        )
        
        # Check user's daily download limit
        if user.daily_downloads >= 50:  # Configurable limit
            await m.reply_text(
                "⚠️ **Daily download limit reached!**\n\n"
                f"You've downloaded {user.daily_downloads} files today.\n"
                "Limit resets at midnight UTC."
            )
            return
        
        # Start the enhanced download process
        await start_enhanced_download_process(bot, m, user)
        
    except Exception as e:
        logger.error(f"Error in enhanced_pro_command: {e}")
        await m.reply_text(f"❌ **Error:** {str(e)}")


async def start_enhanced_download_process(bot: AFK, m: Message, user: User):
    """Start the enhanced download process"""
    
    # Create user download directory
    sPath = f"{Config.DOWNLOAD_LOCATION}/{m.chat.id}"
    os.makedirs(sPath, exist_ok=True)
    
    # Initialize Telegram client
    BOT = TgClient(bot, m, sPath)
    
    try:
        # Get user input with enhanced validation
        nameLinks, num, caption, quality, Token, txt_name, userr = await BOT.Ask_user()
        
        if not nameLinks or len(nameLinks) <= num:
            await m.reply_text("❌ **No valid links found in the file.**")
            return
        
        # Get thumbnail
        Thumb = await BOT.thumb()
        
        # Show download summary
        total_files = len(nameLinks) - num
        summary_msg = await m.reply_text(
            f"📋 **Download Summary**\n\n"
            f"📁 **Batch:** {caption}\n"
            f"📊 **Total Files:** {total_files}\n"
            f"🎯 **Quality:** {quality}\n"
            f"👤 **User:** {userr}\n\n"
            f"⏳ **Adding to download queue...**"
        )
        
        # Add jobs to download manager
        job_ids = []
        for i in range(num, len(nameLinks)):
            try:
                name = BOT.parse_name(nameLinks[i][0])
                link = nameLinks[i][1]
                file_name = f"{str(i+1).zfill(3)}. - {BOT.short_name(name)}"
                
                # Validate URL
                if not security_manager.validate_url(link):
                    logger.warning(f"Invalid URL skipped: {link}")
                    continue
                
                # Add to download queue
                job_id = await download_manager.add_download_job(
                    user_id=user.user_id,
                    course_name=name,
                    course_url=link,
                    file_name=file_name,
                    quality=quality,
                    priority=0  # Normal priority
                )
                
                job_ids.append(job_id)
                
            except Exception as e:
                logger.error(f"Error adding job for {nameLinks[i][0]}: {e}")
                continue
        
        if not job_ids:
            await summary_msg.edit_text("❌ **No valid downloads could be queued.**")
            return
        
        # Update summary with queue information
        await summary_msg.edit_text(
            f"✅ **Downloads Queued Successfully!**\n\n"
            f"📁 **Batch:** {caption}\n"
            f"📊 **Queued:** {len(job_ids)} files\n"
            f"🎯 **Quality:** {quality}\n"
            f"👤 **User:** {userr}\n\n"
            f"🔄 **Status:** Processing in queue\n"
            f"📱 Use `/status` to check progress",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Check Status", callback_data=f"status_{user.user_id}")],
                [InlineKeyboardButton("❌ Cancel All", callback_data=f"cancel_all_{user.user_id}")]
            ])
        )
        
        # Start progress monitoring
        asyncio.create_task(monitor_download_progress(bot, m, job_ids, summary_msg, user, caption, Thumb))
        
    except Exception as e:
        logger.error(f"Error in enhanced download process: {e}")
        await m.reply_text(f"❌ **Error:** {str(e)}")


async def monitor_download_progress(bot: AFK, m: Message, job_ids: list, summary_msg: Message, 
                                  user: User, caption: str, thumb):
    """Monitor download progress and handle uploads"""
    completed_jobs = 0
    failed_jobs = 0
    total_jobs = len(job_ids)
    
    # Progress callback for real-time updates
    def progress_callback(progress: DownloadProgress):
        # This could be used to update progress in real-time
        pass
    
    download_manager.add_progress_callback(progress_callback)
    
    try:
        while completed_jobs + failed_jobs < total_jobs:
            await asyncio.sleep(10)  # Check every 10 seconds
            
            current_completed = 0
            current_failed = 0
            active_downloads = []
            
            for job_id in job_ids:
                job = await db_manager.get_download_job(job_id)
                if job:
                    if job.status == DownloadStatus.COMPLETED:
                        current_completed += 1
                        
                        # Handle upload if newly completed
                        if job_id not in [j.job_id for j in await db_manager.get_user_jobs(user.user_id, DownloadStatus.COMPLETED)]:
                            await handle_completed_download(bot, m, job, user, caption, thumb)
                    
                    elif job.status == DownloadStatus.FAILED:
                        current_failed += 1
                    
                    elif job.status in [DownloadStatus.DOWNLOADING, DownloadStatus.PENDING]:
                        active_downloads.append(job)
            
            # Update progress if changed
            if current_completed != completed_jobs or current_failed != failed_jobs:
                completed_jobs = current_completed
                failed_jobs = current_failed
                
                progress_text = (
                    f"🔄 **Download Progress**\n\n"
                    f"📁 **Batch:** {caption}\n"
                    f"✅ **Completed:** {completed_jobs}/{total_jobs}\n"
                    f"❌ **Failed:** {failed_jobs}/{total_jobs}\n"
                    f"⏳ **Active:** {len(active_downloads)}\n\n"
                )
                
                if active_downloads:
                    progress_text += "**Currently downloading:**\n"
                    for job in active_downloads[:3]:  # Show max 3 active
                        progress_text += f"• {job.file_name[:30]}...\n"
                
                try:
                    await summary_msg.edit_text(
                        progress_text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📊 Detailed Status", callback_data=f"detailed_status_{user.user_id}")],
                            [InlineKeyboardButton("❌ Cancel Remaining", callback_data=f"cancel_remaining_{user.user_id}")]
                        ])
                    )
                except Exception as e:
                    logger.error(f"Error updating progress message: {e}")
        
        # Final summary
        success_rate = (completed_jobs / total_jobs) * 100 if total_jobs > 0 else 0
        final_text = (
            f"🎉 **Batch Completed!**\n\n"
            f"📁 **Batch:** {caption}\n"
            f"✅ **Successful:** {completed_jobs}/{total_jobs}\n"
            f"❌ **Failed:** {failed_jobs}/{total_jobs}\n"
            f"📊 **Success Rate:** {success_rate:.1f}%\n\n"
            f"{'🎊 All files processed successfully!' if failed_jobs == 0 else '⚠️ Some files failed to download.'}"
        )
        
        await summary_msg.edit_text(final_text)
        
    except Exception as e:
        logger.error(f"Error monitoring download progress: {e}")


async def handle_completed_download(bot: AFK, m: Message, job: DownloadJob, user: User, caption: str, thumb):
    """Handle completed download - upload to Telegram"""
    try:
        # Construct file path
        file_path = f"./DOWNLOADS/{job.user_id}/{job.file_name}"
        
        if not os.path.exists(file_path):
            logger.error(f"Completed file not found: {file_path}")
            return
        
        # Prepare upload caption
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        upload_caption = (
            f"{job.file_name}\n\n"
            f"<b>📁 Batch:</b> {caption}\n"
            f"<b>📊 Size:</b> {file_size_mb:.1f} MB\n"
            f"<b>🎯 Quality:</b> {job.quality}\n"
            f"<b>👤 Extracted by:</b> {user.first_name or user.username or 'User'}"
        )
        
        # Determine target chat
        target_chat = user.target_chat_id if user.target_chat_id else m.chat.id
        
        # Upload file
        UL = Upload_to_Tg(
            bot=bot,
            m=m,
            file_path=file_path,
            name=job.file_name,
            Thumb=thumb,
            path=f"./DOWNLOADS/{job.user_id}",
            show_msg=None,
            caption=upload_caption
        )
        
        # Upload based on file type
        file_ext = file_path.split(".")[-1].lower()
        if file_ext in ["mp4", "mkv", "avi", "mov"]:
            await UL.upload_video()
        else:
            await UL.upload_doc()
        
        # Clean up file after upload
        try:
            os.remove(file_path)
            logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up file {file_path}: {e}")
        
        # Update user statistics
        await db_manager.increment_user_downloads(user.user_id, failed=False)
        
    except Exception as e:
        logger.error(f"Error handling completed download {job.job_id}: {e}")


@AFK.on_message(
    (filters.chat(Config.GROUPS) | filters.chat(Config.AUTH_USERS)) &
    filters.incoming & filters.command("status", prefixes=prefixes)
)
@require_auth
async def status_command(bot: AFK, m: Message):
    """Enhanced status command"""
    try:
        await db_manager.connect()
        
        user = await db_manager.get_user(m.from_user.id)
        if not user:
            await m.reply_text("❌ **User not found. Use `/pro_enhanced` first.**")
            return
        
        # Get user's active jobs
        active_jobs = await db_manager.get_user_jobs(user.user_id, DownloadStatus.DOWNLOADING)
        pending_jobs = await db_manager.get_user_jobs(user.user_id, DownloadStatus.PENDING)
        
        # Get system status
        system_status = await download_manager.get_system_status()
        
        # Get user statistics
        user_history = await db_manager.get_user_download_history(user.user_id, limit=10)
        
        status_text = (
            f"📊 **System Status**\n\n"
            f"👤 **User:** {user.first_name or user.username or 'Unknown'}\n"
            f"📈 **Your Stats:**\n"
            f"  • Daily Downloads: {user.daily_downloads}/50\n"
            f"  • Total Downloads: {user.total_downloads}\n"
            f"  • Failed Downloads: {user.total_failed_downloads}\n\n"
            f"🔄 **Current Jobs:**\n"
            f"  • Active: {len(active_jobs)}\n"
            f"  • Pending: {len(pending_jobs)}\n\n"
            f"🖥️ **System:**\n"
            f"  • Active Downloads: {system_status['active_downloads']}\n"
            f"  • Queue Size: {system_status['queue_size']}\n"
            f"  • Memory: {system_status['system_resources']['memory_percent']:.1f}%\n"
            f"  • Disk: {system_status['system_resources']['disk_percent']:.1f}%\n"
        )
        
        if active_jobs:
            status_text += "\n**🔄 Your Active Downloads:**\n"
            for job in active_jobs[:5]:  # Show max 5
                status_text += f"• {job.file_name[:40]}...\n"
        
        await m.reply_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_status_{user.user_id}")],
                [InlineKeyboardButton("📊 Detailed Stats", callback_data=f"detailed_stats_{user.user_id}")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error in status command: {e}")
        await m.reply_text(f"❌ **Error:** {str(e)}")


@AFK.on_message(
    (filters.chat(Config.GROUPS) | filters.chat(Config.AUTH_USERS)) &
    filters.incoming & filters.command("cleanup", prefixes=prefixes)
)
@require_auth
async def cleanup_command(bot: AFK, m: Message):
    """Clean up old files and data"""
    try:
        cleanup_msg = await m.reply_text("🧹 **Starting cleanup...**")
        
        # Clean up old files
        cleaned_files = await download_manager.cleanup_old_files(max_age_hours=24)
        
        # Clean up old database records
        await db_manager.connect()
        cleaned_jobs = await db_manager.cleanup_old_jobs(days=7)
        cleaned_history = await db_manager.cleanup_old_history(days=30)
        
        await cleanup_msg.edit_text(
            f"✅ **Cleanup Completed!**\n\n"
            f"🗑️ **Files Cleaned:** {cleaned_files}\n"
            f"📋 **Old Jobs Cleaned:** {cleaned_jobs}\n"
            f"📊 **Old History Cleaned:** {cleaned_history}\n\n"
            f"💾 **Disk space freed up!**"
        )
        
    except Exception as e:
        logger.error(f"Error in cleanup command: {e}")
        await m.reply_text(f"❌ **Cleanup Error:** {str(e)}")


# Callback query handlers for inline buttons
@AFK.on_callback_query()
async def handle_callback_queries(bot: AFK, callback_query):
    """Handle inline button callbacks"""
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data.startswith("status_"):
            # Refresh status
            await status_command(bot, callback_query.message)
        
        elif data.startswith("cancel_all_"):
            # Cancel all user downloads
            await db_manager.connect()
            user_jobs = await db_manager.get_user_jobs(user_id)
            
            cancelled_count = 0
            for job in user_jobs:
                if job.status in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING]:
                    await download_manager.cancel_download(job.job_id)
                    cancelled_count += 1
            
            await callback_query.answer(f"Cancelled {cancelled_count} downloads")
        
        elif data.startswith("detailed_stats_"):
            # Show detailed statistics
            await show_detailed_stats(bot, callback_query, user_id)
        
        else:
            await callback_query.answer("Unknown action")
    
    except Exception as e:
        logger.error(f"Error handling callback query: {e}")
        await callback_query.answer("Error occurred")


async def show_detailed_stats(bot: AFK, callback_query, user_id: int):
    """Show detailed user statistics"""
    try:
        await db_manager.connect()
        
        user = await db_manager.get_user(user_id)
        if not user:
            await callback_query.answer("User not found")
            return
        
        # Get recent download history
        history = await db_manager.get_user_download_history(user_id, limit=20)
        
        # Calculate statistics
        total_size = sum(h.file_size for h in history) / (1024**3)  # GB
        avg_download_time = sum(h.download_time for h in history) / len(history) if history else 0
        
        stats_text = (
            f"📊 **Detailed Statistics**\n\n"
            f"👤 **User:** {user.first_name or user.username}\n"
            f"📅 **Member Since:** {user.created_at.strftime('%Y-%m-%d')}\n"
            f"🕐 **Last Activity:** {user.last_activity.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📈 **Download Stats:**\n"
            f"  • Total Downloads: {user.total_downloads}\n"
            f"  • Failed Downloads: {user.total_failed_downloads}\n"
            f"  • Success Rate: {(user.total_downloads / (user.total_downloads + user.total_failed_downloads) * 100):.1f}%\n"
            f"  • Total Data: {total_size:.2f} GB\n"
            f"  • Avg Download Time: {avg_download_time:.1f}s\n\n"
            f"⚙️ **Settings:**\n"
            f"  • Preferred Quality: {user.preferred_quality}\n"
            f"  • Target Chat: {'Set' if user.target_chat_id else 'Not Set'}\n"
        )
        
        if history:
            stats_text += f"\n**📋 Recent Downloads:**\n"
            for h in history[:5]:
                status_emoji = "✅" if h.status == DownloadStatus.COMPLETED else "❌"
                stats_text += f"{status_emoji} {h.file_name[:30]}...\n"
        
        await callback_query.message.edit_text(
            stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Status", callback_data=f"status_{user_id}")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error showing detailed stats: {e}")
        await callback_query.answer("Error loading stats")
