"""
Database models for production-ready Telegram bot
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class UserRole(Enum):
    USER = "user"
    ADMIN = "admin"
    PREMIUM = "premium"


@dataclass
class User:
    """User model for storing user information and preferences"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: UserRole = UserRole.USER
    target_chat_id: Optional[int] = None
    preferred_quality: str = "720p"
    classplus_email: Optional[str] = None
    classplus_password_hash: Optional[str] = None  # Never store plain passwords
    classplus_token: Optional[str] = None
    classplus_token_expires: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    
    # Rate limiting
    daily_downloads: int = 0
    daily_downloads_reset: datetime = field(default_factory=datetime.utcnow)
    
    # Statistics
    total_downloads: int = 0
    total_failed_downloads: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "role": self.role.value,
            "target_chat_id": self.target_chat_id,
            "preferred_quality": self.preferred_quality,
            "classplus_email": self.classplus_email,
            "classplus_password_hash": self.classplus_password_hash,
            "classplus_token": self.classplus_token,
            "classplus_token_expires": self.classplus_token_expires,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity": self.last_activity,
            "daily_downloads": self.daily_downloads,
            "daily_downloads_reset": self.daily_downloads_reset,
            "total_downloads": self.total_downloads,
            "total_failed_downloads": self.total_failed_downloads
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Create User from dictionary"""
        return cls(
            user_id=data["user_id"],
            username=data.get("username"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            role=UserRole(data.get("role", "user")),
            target_chat_id=data.get("target_chat_id"),
            preferred_quality=data.get("preferred_quality", "720p"),
            classplus_email=data.get("classplus_email"),
            classplus_password_hash=data.get("classplus_password_hash"),
            classplus_token=data.get("classplus_token"),
            classplus_token_expires=data.get("classplus_token_expires"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", datetime.utcnow()),
            updated_at=data.get("updated_at", datetime.utcnow()),
            last_activity=data.get("last_activity", datetime.utcnow()),
            daily_downloads=data.get("daily_downloads", 0),
            daily_downloads_reset=data.get("daily_downloads_reset", datetime.utcnow()),
            total_downloads=data.get("total_downloads", 0),
            total_failed_downloads=data.get("total_failed_downloads", 0)
        )


@dataclass
class DownloadJob:
    """Download job model for queue management"""
    job_id: str
    user_id: int
    course_name: str
    course_url: str
    file_name: str
    quality: str
    status: DownloadStatus = DownloadStatus.PENDING
    priority: int = 0  # Higher number = higher priority
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    downloaded_bytes: int = 0
    download_speed: Optional[float] = None
    eta: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "course_name": self.course_name,
            "course_url": self.course_url,
            "file_name": self.file_name,
            "quality": self.quality,
            "status": self.status.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "file_size": self.file_size,
            "downloaded_bytes": self.downloaded_bytes,
            "download_speed": self.download_speed,
            "eta": self.eta,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadJob':
        """Create DownloadJob from dictionary"""
        return cls(
            job_id=data["job_id"],
            user_id=data["user_id"],
            course_name=data["course_name"],
            course_url=data["course_url"],
            file_name=data["file_name"],
            quality=data["quality"],
            status=DownloadStatus(data.get("status", "pending")),
            priority=data.get("priority", 0),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            error_message=data.get("error_message"),
            file_size=data.get("file_size"),
            downloaded_bytes=data.get("downloaded_bytes", 0),
            download_speed=data.get("download_speed"),
            eta=data.get("eta"),
            created_at=data.get("created_at", datetime.utcnow()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at")
        )


@dataclass
class DownloadHistory:
    """Download history for tracking completed downloads"""
    user_id: int
    job_id: str
    course_name: str
    file_name: str
    file_size: int
    download_time: float  # seconds
    quality: str
    status: DownloadStatus
    error_message: Optional[str] = None
    completed_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        return {
            "user_id": self.user_id,
            "job_id": self.job_id,
            "course_name": self.course_name,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "download_time": self.download_time,
            "quality": self.quality,
            "status": self.status.value,
            "error_message": self.error_message,
            "completed_at": self.completed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadHistory':
        """Create DownloadHistory from dictionary"""
        return cls(
            user_id=data["user_id"],
            job_id=data["job_id"],
            course_name=data["course_name"],
            file_name=data["file_name"],
            file_size=data["file_size"],
            download_time=data["download_time"],
            quality=data["quality"],
            status=DownloadStatus(data["status"]),
            error_message=data.get("error_message"),
            completed_at=data.get("completed_at", datetime.utcnow())
        )


@dataclass
class SystemStats:
    """System statistics for monitoring"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    active_downloads: int = 0
    queued_downloads: int = 0
    total_users: int = 0
    active_users_24h: int = 0
    disk_usage_gb: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage"""
        return {
            "timestamp": self.timestamp,
            "active_downloads": self.active_downloads,
            "queued_downloads": self.queued_downloads,
            "total_users": self.total_users,
            "active_users_24h": self.active_users_24h,
            "disk_usage_gb": self.disk_usage_gb,
            "memory_usage_mb": self.memory_usage_mb,
            "cpu_usage_percent": self.cpu_usage_percent
        }
