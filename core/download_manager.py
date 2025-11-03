"""
Production-ready download manager with retry mechanisms and error recovery
"""
import os
import asyncio
import logging
import time
import uuid
import shutil
import psutil
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from pathlib import Path
import aiofiles
import aiohttp
from concurrent.futures import ThreadPoolExecutor

from database.database import db_manager
from database.models import DownloadJob, DownloadStatus, DownloadHistory
from handlers.downloader import download_handler

logger = logging.getLogger(__name__)


@dataclass
class DownloadProgress:
    """Download progress information"""
    job_id: str
    file_name: str
    total_size: int = 0
    downloaded_size: int = 0
    speed: float = 0.0
    eta: int = 0
    percentage: float = 0.0
    status: str = "starting"


class CircuitBreaker:
    """Circuit breaker pattern for handling external service failures"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"


class RateLimiter:
    """Rate limiter for controlling download frequency"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    async def acquire(self) -> bool:
        """Acquire permission to make a request"""
        now = time.time()
        
        # Remove old requests outside the time window
        self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        
        return False
    
    async def wait_if_needed(self):
        """Wait if rate limit is exceeded"""
        while not await self.acquire():
            await asyncio.sleep(1)


class ResourceMonitor:
    """Monitor system resources to prevent overload"""
    
    def __init__(self, max_memory_percent: float = 80.0, max_disk_percent: float = 90.0):
        self.max_memory_percent = max_memory_percent
        self.max_disk_percent = max_disk_percent
    
    def check_resources(self) -> Dict[str, Any]:
        """Check current system resources"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu = psutil.cpu_percent(interval=1)
        
        return {
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "disk_percent": disk.percent,
            "disk_free_gb": disk.free / (1024**3),
            "cpu_percent": cpu,
            "can_download": (
                memory.percent < self.max_memory_percent and 
                disk.percent < self.max_disk_percent
            )
        }
    
    def get_system_stats(self) -> Dict[str, float]:
        """Get system statistics for monitoring"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu = psutil.cpu_percent()
        
        return {
            "memory_usage_mb": memory.used / (1024**2),
            "disk_usage_gb": disk.used / (1024**3),
            "cpu_usage_percent": cpu
        }


class EnhancedDownloadManager:
    """Production-ready download manager with advanced features"""
    
    def __init__(self, max_concurrent_downloads: int = 3, download_timeout: int = 3600):
        self.max_concurrent_downloads = max_concurrent_downloads
        self.download_timeout = download_timeout
        self.active_downloads: Dict[str, DownloadProgress] = {}
        self.download_queue = asyncio.Queue()
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter()
        self.resource_monitor = ResourceMonitor()
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_downloads)
        self._running = False
        self._workers = []
        
        # Progress callbacks
        self.progress_callbacks: List[Callable[[DownloadProgress], None]] = []
    
    async def start(self):
        """Start the download manager"""
        if self._running:
            return
        
        self._running = True
        
        # Start worker tasks
        for i in range(self.max_concurrent_downloads):
            worker = asyncio.create_task(self._download_worker(f"worker-{i}"))
            self._workers.append(worker)
        
        logger.info(f"Download manager started with {self.max_concurrent_downloads} workers")
    
    async def stop(self):
        """Stop the download manager"""
        self._running = False
        
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("Download manager stopped")
    
    def add_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """Add progress callback"""
        self.progress_callbacks.append(callback)
    
    def _notify_progress(self, progress: DownloadProgress):
        """Notify all progress callbacks"""
        for callback in self.progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    async def add_download_job(self, user_id: int, course_name: str, course_url: str, 
                             file_name: str, quality: str = "720p", priority: int = 0) -> str:
        """Add a new download job to the queue"""
        job_id = str(uuid.uuid4())
        
        job = DownloadJob(
            job_id=job_id,
            user_id=user_id,
            course_name=course_name,
            course_url=course_url,
            file_name=file_name,
            quality=quality,
            priority=priority
        )
        
        # Save to database
        await db_manager.create_download_job(job)
        
        # Add to queue
        await self.download_queue.put(job)
        
        logger.info(f"Added download job {job_id} for user {user_id}")
        return job_id
    
    async def get_download_progress(self, job_id: str) -> Optional[DownloadProgress]:
        """Get download progress for a job"""
        return self.active_downloads.get(job_id)
    
    async def get_user_downloads(self, user_id: int) -> List[DownloadJob]:
        """Get all downloads for a user"""
        return await db_manager.get_user_jobs(user_id)
    
    async def cancel_download(self, job_id: str) -> bool:
        """Cancel a download job"""
        # Remove from active downloads
        if job_id in self.active_downloads:
            del self.active_downloads[job_id]
        
        # Update database
        await db_manager.update_download_job(job_id, status=DownloadStatus.FAILED.value, error_message="Cancelled by user")
        
        logger.info(f"Cancelled download job {job_id}")
        return True
    
    async def _download_worker(self, worker_name: str):
        """Download worker that processes jobs from the queue"""
        logger.info(f"Download worker {worker_name} started")
        
        while self._running:
            try:
                # Get job from queue with timeout
                try:
                    job = await asyncio.wait_for(self.download_queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                
                # Check if we can execute (circuit breaker)
                if not self.circuit_breaker.can_execute():
                    logger.warning(f"Circuit breaker is OPEN, requeueing job {job.job_id}")
                    await self.download_queue.put(job)
                    await asyncio.sleep(10)
                    continue
                
                # Check system resources
                resources = self.resource_monitor.check_resources()
                if not resources["can_download"]:
                    logger.warning(f"System resources low, requeueing job {job.job_id}")
                    await self.download_queue.put(job)
                    await asyncio.sleep(30)
                    continue
                
                # Rate limiting
                await self.rate_limiter.wait_if_needed()
                
                # Process the download
                await self._process_download_job(job, worker_name)
                
            except Exception as e:
                logger.error(f"Error in download worker {worker_name}: {e}")
                await asyncio.sleep(5)
        
        logger.info(f"Download worker {worker_name} stopped")
    
    async def _process_download_job(self, job: DownloadJob, worker_name: str):
        """Process a single download job with retry logic"""
        logger.info(f"Worker {worker_name} processing job {job.job_id}")
        
        # Create progress tracker
        progress = DownloadProgress(
            job_id=job.job_id,
            file_name=job.file_name,
            status="starting"
        )
        self.active_downloads[job.job_id] = progress
        
        # Update job status
        await db_manager.update_download_job(
            job.job_id,
            status=DownloadStatus.DOWNLOADING.value,
            started_at=datetime.utcnow()
        )
        
        start_time = time.time()
        success = False
        error_message = None
        file_path = None
        
        try:
            # Create user download directory
            user_dir = Path(f"./DOWNLOADS/{job.user_id}")
            user_dir.mkdir(parents=True, exist_ok=True)
            
            # Attempt download with retries
            for attempt in range(job.max_retries + 1):
                try:
                    logger.info(f"Download attempt {attempt + 1}/{job.max_retries + 1} for job {job.job_id}")
                    
                    progress.status = f"downloading (attempt {attempt + 1})"
                    self._notify_progress(progress)
                    
                    # Use existing download handler with enhancements
                    file_path = await self._download_with_progress(job, progress, str(user_dir))
                    
                    if file_path and os.path.exists(file_path):
                        success = True
                        self.circuit_breaker.record_success()
                        break
                    else:
                        raise Exception("Download completed but file not found")
                
                except Exception as e:
                    error_message = str(e)
                    logger.error(f"Download attempt {attempt + 1} failed for job {job.job_id}: {e}")
                    
                    if attempt < job.max_retries:
                        # Exponential backoff
                        wait_time = min(300, (2 ** attempt) * 10)  # Max 5 minutes
                        logger.info(f"Retrying job {job.job_id} in {wait_time} seconds")
                        
                        progress.status = f"retrying in {wait_time}s"
                        self._notify_progress(progress)
                        
                        await asyncio.sleep(wait_time)
                    else:
                        self.circuit_breaker.record_failure()
            
            # Update job status based on result
            if success:
                file_size = os.path.getsize(file_path) if file_path else 0
                download_time = time.time() - start_time
                
                await db_manager.update_download_job(
                    job.job_id,
                    status=DownloadStatus.COMPLETED.value,
                    completed_at=datetime.utcnow(),
                    file_size=file_size
                )
                
                # Add to download history
                history = DownloadHistory(
                    user_id=job.user_id,
                    job_id=job.job_id,
                    course_name=job.course_name,
                    file_name=job.file_name,
                    file_size=file_size,
                    download_time=download_time,
                    quality=job.quality,
                    status=DownloadStatus.COMPLETED
                )
                await db_manager.add_download_history(history)
                
                # Update user statistics
                await db_manager.increment_user_downloads(job.user_id, failed=False)
                
                progress.status = "completed"
                progress.percentage = 100.0
                self._notify_progress(progress)
                
                logger.info(f"Successfully completed download job {job.job_id}")
                
                # Return file path for upload
                return file_path
            
            else:
                await db_manager.update_download_job(
                    job.job_id,
                    status=DownloadStatus.FAILED.value,
                    error_message=error_message,
                    completed_at=datetime.utcnow(),
                    retry_count=job.max_retries
                )
                
                # Update user statistics
                await db_manager.increment_user_downloads(job.user_id, failed=True)
                
                progress.status = "failed"
                self._notify_progress(progress)
                
                logger.error(f"Failed to download job {job.job_id} after {job.max_retries} retries")
        
        except Exception as e:
            logger.error(f"Unexpected error processing job {job.job_id}: {e}")
            
            await db_manager.update_download_job(
                job.job_id,
                status=DownloadStatus.FAILED.value,
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
            
            progress.status = "error"
            self._notify_progress(progress)
        
        finally:
            # Remove from active downloads
            if job.job_id in self.active_downloads:
                del self.active_downloads[job.job_id]
    
    async def _download_with_progress(self, job: DownloadJob, progress: DownloadProgress, download_path: str) -> str:
        """Download with progress tracking"""
        # Use existing download handler but with progress tracking
        DL = download_handler(
            name=job.file_name,
            url=job.course_url,
            path=download_path,
            Token="",  # Will be handled by the download handler
            Quality=job.quality
        )
        
        # Start download in executor to avoid blocking
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(
            self.executor,
            DL.start_download
        )
        
        return file_path
    
    async def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old downloaded files"""
        downloads_dir = Path("./DOWNLOADS")
        if not downloads_dir.exists():
            return
        
        cutoff_time = time.time() - (max_age_hours * 3600)
        cleaned_count = 0
        
        for user_dir in downloads_dir.iterdir():
            if user_dir.is_dir():
                for file_path in user_dir.iterdir():
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                        try:
                            file_path.unlink()
                            cleaned_count += 1
                        except Exception as e:
                            logger.error(f"Error deleting old file {file_path}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} old files")
        return cleaned_count
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get current system status"""
        resources = self.resource_monitor.check_resources()
        
        return {
            "active_downloads": len(self.active_downloads),
            "queue_size": self.download_queue.qsize(),
            "circuit_breaker_state": self.circuit_breaker.state,
            "system_resources": resources,
            "workers_running": len([w for w in self._workers if not w.done()]),
            "is_running": self._running
        }


# Global download manager instance
download_manager = EnhancedDownloadManager()
