"""
Production-ready database layer with MongoDB integration
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import hashlib
import secrets
from .models import User, DownloadJob, DownloadHistory, SystemStats, DownloadStatus, UserRole

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Production-ready database manager with connection pooling and error handling"""
    
    def __init__(self, mongo_uri: str = None):
        self.mongo_uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        self.database_name = os.environ.get("MONGO_DB_NAME", "telegram_bot")
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self._collections: Dict[str, AsyncIOMotorCollection] = {}
        self._connection_lock = asyncio.Lock()
        
    async def connect(self):
        """Establish database connection with retry logic"""
        async with self._connection_lock:
            if self.client is not None:
                return
                
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.client = AsyncIOMotorClient(
                        self.mongo_uri,
                        maxPoolSize=50,
                        minPoolSize=10,
                        maxIdleTimeMS=30000,
                        serverSelectionTimeoutMS=5000,
                        connectTimeoutMS=10000,
                        socketTimeoutMS=20000
                    )
                    
                    # Test connection
                    await self.client.admin.command('ping')
                    
                    self.db = self.client[self.database_name]
                    
                    # Initialize collections
                    self._collections = {
                        'users': self.db.users,
                        'download_jobs': self.db.download_jobs,
                        'download_history': self.db.download_history,
                        'system_stats': self.db.system_stats
                    }
                    
                    # Create indexes for better performance
                    await self._create_indexes()
                    
                    logger.info(f"Connected to MongoDB: {self.database_name}")
                    return
                    
                except Exception as e:
                    logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    async def disconnect(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self._collections.clear()
            logger.info("Disconnected from MongoDB")
    
    async def _create_indexes(self):
        """Create database indexes for optimal performance"""
        try:
            # Users collection indexes
            await self._collections['users'].create_index("user_id", unique=True)
            await self._collections['users'].create_index("username")
            await self._collections['users'].create_index("last_activity")
            await self._collections['users'].create_index("daily_downloads_reset")
            
            # Download jobs collection indexes
            await self._collections['download_jobs'].create_index("job_id", unique=True)
            await self._collections['download_jobs'].create_index("user_id")
            await self._collections['download_jobs'].create_index("status")
            await self._collections['download_jobs'].create_index([("priority", -1), ("created_at", 1)])
            await self._collections['download_jobs'].create_index("created_at")
            
            # Download history collection indexes
            await self._collections['download_history'].create_index("user_id")
            await self._collections['download_history'].create_index("completed_at")
            await self._collections['download_history'].create_index("job_id")
            
            # System stats collection indexes
            await self._collections['system_stats'].create_index("timestamp")
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating database indexes: {e}")
    
    async def _ensure_connection(self):
        """Ensure database connection is active"""
        if self.client is None:
            await self.connect()
    
    # User management methods
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """Create a new user"""
        await self._ensure_connection()
        
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        
        try:
            await self._collections['users'].insert_one(user.to_dict())
            logger.info(f"Created new user: {user_id}")
            return user
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise
    
    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        await self._ensure_connection()
        
        try:
            user_data = await self._collections['users'].find_one({"user_id": user_id})
            if user_data:
                return User.from_dict(user_data)
            return None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        await self._ensure_connection()
        
        try:
            kwargs['updated_at'] = datetime.utcnow()
            result = await self._collections['users'].update_one(
                {"user_id": user_id},
                {"$set": kwargs}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False
    
    async def update_user_activity(self, user_id: int):
        """Update user's last activity timestamp"""
        await self.update_user(user_id, last_activity=datetime.utcnow())
    
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """Get existing user or create new one"""
        user = await self.get_user(user_id)
        if user is None:
            user = await self.create_user(user_id, username, first_name, last_name)
        else:
            # Update user activity
            await self.update_user_activity(user_id)
        return user
    
    async def set_user_classplus_credentials(self, user_id: int, email: str, password: str) -> bool:
        """Set user's Classplus credentials (password is hashed)"""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return await self.update_user(
            user_id,
            classplus_email=email,
            classplus_password_hash=password_hash
        )
    
    async def set_user_target_chat(self, user_id: int, target_chat_id: int) -> bool:
        """Set user's target chat for uploads"""
        return await self.update_user(user_id, target_chat_id=target_chat_id)
    
    async def increment_user_downloads(self, user_id: int, failed: bool = False):
        """Increment user's download counters"""
        await self._ensure_connection()
        
        try:
            now = datetime.utcnow()
            user = await self.get_user(user_id)
            
            if user and user.daily_downloads_reset.date() < now.date():
                # Reset daily counter if it's a new day
                await self.update_user(
                    user_id,
                    daily_downloads=1 if not failed else 0,
                    daily_downloads_reset=now,
                    total_downloads=user.total_downloads + (1 if not failed else 0),
                    total_failed_downloads=user.total_failed_downloads + (1 if failed else 0)
                )
            else:
                # Increment counters
                increment_data = {
                    "daily_downloads": 1 if not failed else 0,
                    "total_downloads": 1 if not failed else 0,
                    "total_failed_downloads": 1 if failed else 0
                }
                
                await self._collections['users'].update_one(
                    {"user_id": user_id},
                    {"$inc": increment_data}
                )
        except Exception as e:
            logger.error(f"Error incrementing user downloads {user_id}: {e}")
    
    # Download job management methods
    async def create_download_job(self, job: DownloadJob) -> bool:
        """Create a new download job"""
        await self._ensure_connection()
        
        try:
            await self._collections['download_jobs'].insert_one(job.to_dict())
            logger.info(f"Created download job: {job.job_id}")
            return True
        except Exception as e:
            logger.error(f"Error creating download job {job.job_id}: {e}")
            return False
    
    async def get_download_job(self, job_id: str) -> Optional[DownloadJob]:
        """Get download job by ID"""
        await self._ensure_connection()
        
        try:
            job_data = await self._collections['download_jobs'].find_one({"job_id": job_id})
            if job_data:
                return DownloadJob.from_dict(job_data)
            return None
        except Exception as e:
            logger.error(f"Error getting download job {job_id}: {e}")
            return None
    
    async def update_download_job(self, job_id: str, **kwargs) -> bool:
        """Update download job"""
        await self._ensure_connection()
        
        try:
            result = await self._collections['download_jobs'].update_one(
                {"job_id": job_id},
                {"$set": kwargs}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating download job {job_id}: {e}")
            return False
    
    async def get_pending_jobs(self, limit: int = 10) -> List[DownloadJob]:
        """Get pending download jobs ordered by priority and creation time"""
        await self._ensure_connection()
        
        try:
            cursor = self._collections['download_jobs'].find(
                {"status": DownloadStatus.PENDING.value}
            ).sort([("priority", -1), ("created_at", 1)]).limit(limit)
            
            jobs = []
            async for job_data in cursor:
                jobs.append(DownloadJob.from_dict(job_data))
            
            return jobs
        except Exception as e:
            logger.error(f"Error getting pending jobs: {e}")
            return []
    
    async def get_user_jobs(self, user_id: int, status: DownloadStatus = None) -> List[DownloadJob]:
        """Get user's download jobs"""
        await self._ensure_connection()
        
        try:
            query = {"user_id": user_id}
            if status:
                query["status"] = status.value
            
            cursor = self._collections['download_jobs'].find(query).sort("created_at", -1)
            
            jobs = []
            async for job_data in cursor:
                jobs.append(DownloadJob.from_dict(job_data))
            
            return jobs
        except Exception as e:
            logger.error(f"Error getting user jobs {user_id}: {e}")
            return []
    
    async def delete_download_job(self, job_id: str) -> bool:
        """Delete download job"""
        await self._ensure_connection()
        
        try:
            result = await self._collections['download_jobs'].delete_one({"job_id": job_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting download job {job_id}: {e}")
            return False
    
    # Download history methods
    async def add_download_history(self, history: DownloadHistory) -> bool:
        """Add download to history"""
        await self._ensure_connection()
        
        try:
            await self._collections['download_history'].insert_one(history.to_dict())
            return True
        except Exception as e:
            logger.error(f"Error adding download history: {e}")
            return False
    
    async def get_user_download_history(self, user_id: int, limit: int = 50) -> List[DownloadHistory]:
        """Get user's download history"""
        await self._ensure_connection()
        
        try:
            cursor = self._collections['download_history'].find(
                {"user_id": user_id}
            ).sort("completed_at", -1).limit(limit)
            
            history = []
            async for history_data in cursor:
                history.append(DownloadHistory.from_dict(history_data))
            
            return history
        except Exception as e:
            logger.error(f"Error getting user download history {user_id}: {e}")
            return []
    
    # System statistics methods
    async def save_system_stats(self, stats: SystemStats) -> bool:
        """Save system statistics"""
        await self._ensure_connection()
        
        try:
            await self._collections['system_stats'].insert_one(stats.to_dict())
            return True
        except Exception as e:
            logger.error(f"Error saving system stats: {e}")
            return False
    
    async def get_system_stats(self, hours: int = 24) -> List[SystemStats]:
        """Get system statistics for the last N hours"""
        await self._ensure_connection()
        
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            cursor = self._collections['system_stats'].find(
                {"timestamp": {"$gte": since}}
            ).sort("timestamp", -1)
            
            stats = []
            async for stats_data in cursor:
                stats.append(SystemStats(**stats_data))
            
            return stats
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return []
    
    # Cleanup methods
    async def cleanup_old_jobs(self, days: int = 7):
        """Clean up old completed/failed jobs"""
        await self._ensure_connection()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            result = await self._collections['download_jobs'].delete_many({
                "status": {"$in": [DownloadStatus.COMPLETED.value, DownloadStatus.FAILED.value]},
                "completed_at": {"$lt": cutoff_date}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} old download jobs")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")
            return 0
    
    async def cleanup_old_history(self, days: int = 30):
        """Clean up old download history"""
        await self._ensure_connection()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            result = await self._collections['download_history'].delete_many({
                "completed_at": {"$lt": cutoff_date}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} old download history records")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old history: {e}")
            return 0
    
    async def cleanup_old_stats(self, days: int = 7):
        """Clean up old system statistics"""
        await self._ensure_connection()
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            result = await self._collections['system_stats'].delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            logger.info(f"Cleaned up {result.deleted_count} old system stats records")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old stats: {e}")
            return 0


# Global database instance
db_manager = DatabaseManager()
