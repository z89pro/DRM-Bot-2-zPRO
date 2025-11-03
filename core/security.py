"""
Security layer for production-ready bot
"""
import os
import hashlib
import secrets
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """Rate limit information for a user"""
    requests: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    blocked_until: Optional[datetime] = None


class SecurityManager:
    """Production-ready security manager"""
    
    def __init__(self):
        # Rate limiting
        self.rate_limits: Dict[int, RateLimitInfo] = {}
        self.global_rate_limit = RateLimitInfo()
        
        # Security settings
        self.max_requests_per_minute = int(os.environ.get("MAX_REQUESTS_PER_MINUTE", "10"))
        self.max_requests_per_hour = int(os.environ.get("MAX_REQUESTS_PER_HOUR", "100"))
        self.max_global_requests_per_minute = int(os.environ.get("MAX_GLOBAL_REQUESTS_PER_MINUTE", "50"))
        
        # Blocked users and IPs
        self.blocked_users: Set[int] = set()
        self.blocked_ips: Set[str] = set()
        
        # Failed login attempts
        self.failed_attempts: Dict[int, int] = {}
        self.max_failed_attempts = 5
        self.lockout_duration = timedelta(minutes=30)
        
        # Suspicious activity detection
        self.suspicious_activity: Dict[int, List[datetime]] = {}
        
    def hash_password(self, password: str, salt: str = None) -> tuple[str, str]:
        """Hash password with salt"""
        if salt is None:
            salt = secrets.token_hex(32)
        
        # Use PBKDF2 with SHA-256
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # iterations
        )
        
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash"""
        try:
            computed_hash, _ = self.hash_password(password, salt)
            return secrets.compare_digest(password_hash, computed_hash)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Check if user is blocked"""
        return user_id in self.blocked_users
    
    def block_user(self, user_id: int, reason: str = "Security violation"):
        """Block a user"""
        self.blocked_users.add(user_id)
        logger.warning(f"Blocked user {user_id}: {reason}")
    
    def unblock_user(self, user_id: int):
        """Unblock a user"""
        self.blocked_users.discard(user_id)
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]
        logger.info(f"Unblocked user {user_id}")
    
    def check_rate_limit(self, user_id: int) -> tuple[bool, str]:
        """Check if user is within rate limits"""
        now = datetime.utcnow()
        
        # Check global rate limit
        if self._check_global_rate_limit(now):
            return False, "System is busy, please try again later"
        
        # Get or create user rate limit info
        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = RateLimitInfo()
        
        user_limit = self.rate_limits[user_id]
        
        # Check if user is temporarily blocked
        if user_limit.blocked_until and now < user_limit.blocked_until:
            remaining = (user_limit.blocked_until - now).total_seconds()
            return False, f"Rate limited. Try again in {int(remaining)} seconds"
        
        # Reset window if needed
        if now - user_limit.window_start > timedelta(minutes=1):
            user_limit.requests = 0
            user_limit.window_start = now
            user_limit.blocked_until = None
        
        # Check rate limit
        if user_limit.requests >= self.max_requests_per_minute:
            # Block user for 5 minutes
            user_limit.blocked_until = now + timedelta(minutes=5)
            logger.warning(f"Rate limited user {user_id}")
            return False, "Too many requests. Please wait 5 minutes"
        
        # Increment request count
        user_limit.requests += 1
        self._increment_global_rate_limit(now)
        
        return True, ""
    
    def _check_global_rate_limit(self, now: datetime) -> bool:
        """Check global rate limit"""
        if now - self.global_rate_limit.window_start > timedelta(minutes=1):
            self.global_rate_limit.requests = 0
            self.global_rate_limit.window_start = now
        
        return self.global_rate_limit.requests >= self.max_global_requests_per_minute
    
    def _increment_global_rate_limit(self, now: datetime):
        """Increment global rate limit counter"""
        if now - self.global_rate_limit.window_start > timedelta(minutes=1):
            self.global_rate_limit.requests = 0
            self.global_rate_limit.window_start = now
        
        self.global_rate_limit.requests += 1
    
    def record_failed_login(self, user_id: int) -> bool:
        """Record failed login attempt, return True if user should be blocked"""
        if user_id not in self.failed_attempts:
            self.failed_attempts[user_id] = 0
        
        self.failed_attempts[user_id] += 1
        
        if self.failed_attempts[user_id] >= self.max_failed_attempts:
            self.block_user(user_id, "Too many failed login attempts")
            return True
        
        return False
    
    def record_successful_login(self, user_id: int):
        """Record successful login (clears failed attempts)"""
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]
    
    def detect_suspicious_activity(self, user_id: int, activity_type: str) -> bool:
        """Detect suspicious activity patterns"""
        now = datetime.utcnow()
        
        if user_id not in self.suspicious_activity:
            self.suspicious_activity[user_id] = []
        
        # Clean old activities (older than 1 hour)
        self.suspicious_activity[user_id] = [
            activity_time for activity_time in self.suspicious_activity[user_id]
            if now - activity_time < timedelta(hours=1)
        ]
        
        # Add current activity
        self.suspicious_activity[user_id].append(now)
        
        # Check for suspicious patterns
        recent_activities = [
            activity_time for activity_time in self.suspicious_activity[user_id]
            if now - activity_time < timedelta(minutes=10)
        ]
        
        # If more than 20 activities in 10 minutes, it's suspicious
        if len(recent_activities) > 20:
            logger.warning(f"Suspicious activity detected for user {user_id}: {activity_type}")
            return True
        
        return False
    
    def sanitize_input(self, text: str, max_length: int = 1000) -> str:
        """Sanitize user input"""
        if not text:
            return ""
        
        # Remove null bytes and control characters
        sanitized = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        
        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized.strip()
    
    def validate_url(self, url: str) -> bool:
        """Validate URL for security"""
        if not url:
            return False
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = [
            'javascript:',
            'data:',
            'file:',
            'ftp:',
            'localhost',
            '127.0.0.1',
            '0.0.0.0'
        ]
        
        url_lower = url.lower()
        for pattern in suspicious_patterns:
            if pattern in url_lower:
                return False
        
        return True
    
    def log_security_event(self, user_id: int, event_type: str, details: str):
        """Log security events"""
        logger.warning(f"SECURITY EVENT - User: {user_id}, Type: {event_type}, Details: {details}")
    
    def get_security_stats(self) -> Dict[str, int]:
        """Get security statistics"""
        return {
            "blocked_users": len(self.blocked_users),
            "users_with_failed_attempts": len(self.failed_attempts),
            "users_with_suspicious_activity": len(self.suspicious_activity),
            "total_rate_limited_users": len([
                user_id for user_id, limit_info in self.rate_limits.items()
                if limit_info.blocked_until and datetime.utcnow() < limit_info.blocked_until
            ])
        }


# Global security manager instance
security_manager = SecurityManager()


def require_auth(func):
    """Decorator to require authentication"""
    @wraps(func)
    async def wrapper(bot, message, *args, **kwargs):
        user_id = message.from_user.id
        
        # Check if user is blocked
        if security_manager.is_user_blocked(user_id):
            await message.reply_text("❌ Access denied. You have been blocked.")
            return
        
        # Check rate limits
        allowed, reason = security_manager.check_rate_limit(user_id)
        if not allowed:
            await message.reply_text(f"❌ {reason}")
            return
        
        # Check for suspicious activity
        if security_manager.detect_suspicious_activity(user_id, func.__name__):
            security_manager.log_security_event(
                user_id, 
                "suspicious_activity", 
                f"Rapid requests to {func.__name__}"
            )
            await message.reply_text("❌ Suspicious activity detected. Please slow down.")
            return
        
        return await func(bot, message, *args, **kwargs)
    
    return wrapper


def admin_only(func):
    """Decorator to restrict access to admins only"""
    @wraps(func)
    async def wrapper(bot, message, *args, **kwargs):
        user_id = message.from_user.id
        
        # Check if user is admin (you can customize this logic)
        admin_users = [int(x) for x in os.environ.get("ADMIN_USERS", "").split(",") if x.strip()]
        
        if user_id not in admin_users:
            security_manager.log_security_event(
                user_id,
                "unauthorized_admin_access",
                f"Attempted to access admin function: {func.__name__}"
            )
            await message.reply_text("❌ Admin access required.")
            return
        
        return await func(bot, message, *args, **kwargs)
    
    return wrapper


def secure_input(max_length: int = 1000):
    """Decorator to sanitize input"""
    def decorator(func):
        @wraps(func)
        async def wrapper(bot, message, *args, **kwargs):
            # Sanitize message text
            if hasattr(message, 'text') and message.text:
                message.text = security_manager.sanitize_input(message.text, max_length)
            
            # Sanitize caption
            if hasattr(message, 'caption') and message.caption:
                message.caption = security_manager.sanitize_input(message.caption, max_length)
            
            return await func(bot, message, *args, **kwargs)
        
        return wrapper
    return decorator
