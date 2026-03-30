"""
Rate Limiter for hourly video generation control.

Stores state in-memory with persistence to client-side localStorage via API.
Limits the number of videos that can be generated per hour.
"""

import time
from datetime import datetime
from typing import Optional
from loguru import logger


class RateLimiter:
    """
    Rate limiter that tracks video generation usage per hour.
    
    The limit resets at the beginning of each hour (XX:00).
    Usage is tracked in-memory and synchronized with frontend via localStorage.
    """
    
    def __init__(self):
        # In-memory storage for rate limit state
        self._limit = 2  # Default: 2 videos per hour (user-configurable 1-3)
        self._used = 0   # Videos generated in current hour
        self._hour_key = self._get_current_hour_key()
        self._last_checked = time.time()
        
        logger.info(f"[RateLimiter] Initialized with limit={self._limit}, hour_key={self._hour_key}")
    
    def _get_current_hour_key(self) -> str:
        """
        Generate hour key in format: YYYY-MM-DD-HH
        
        Example: "2024-03-30-14" for 2:00 PM - 2:59 PM on March 30, 2024
        """
        now = datetime.now()
        return f"{now.year}-{now.month:02d}-{now.day:02d}-{now.hour:02d}"
    
    def _check_and_reset_hour(self) -> bool:
        """
        Check if we've entered a new hour and reset counter if needed.
        
        Returns:
            bool: True if hour was reset, False otherwise
        """
        current_hour_key = self._get_current_hour_key()
        
        if current_hour_key != self._hour_key:
            old_hour = self._hour_key
            self._hour_key = current_hour_key
            old_used = self._used
            self._used = 0
            
            logger.info(
                f"[RateLimiter] Hour changed: {old_hour} → {current_hour_key}. "
                f"Reset usage from {old_used} to 0"
            )
            return True
        
        return False
    
    def get_status(self) -> dict:
        """
        Get current rate limit status.
        
        Returns:
            dict with keys: limit, used, remaining, hour_key, next_reset
        """
        # Check if hour has changed
        self._check_and_reset_hour()
        
        remaining = max(0, self._limit - self._used)
        
        # Calculate next reset time (start of next hour)
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0:
            from datetime import timedelta
            next_hour += timedelta(hours=1)
        
        return {
            "limit": self._limit,
            "used": self._used,
            "remaining": remaining,
            "hour_key": self._hour_key,
            "next_reset": next_hour.isoformat(),
        }
    
    def set_limit(self, limit: int) -> bool:
        """
        Set the hourly generation limit.
        
        Args:
            limit: New limit (must be 1, 2, or 3)
            
        Returns:
            bool: True if limit was set successfully
        """
        if limit not in (1, 2, 3):
            logger.warning(f"[RateLimiter] Invalid limit: {limit}. Must be 1, 2, or 3.")
            return False
        
        old_limit = self._limit
        self._limit = limit
        
        logger.info(f"[RateLimiter] Limit changed: {old_limit} → {limit}")
        return True
    
    def check_allowed(self) -> tuple[bool, str]:
        """
        Check if a new video generation is allowed.
        
        Returns:
            tuple: (allowed: bool, reason: str)
        """
        # Check if hour has changed
        self._check_and_reset_hour()
        
        if self._used < self._limit:
            return True, "Generation allowed"
        else:
            return False, f"Hourly limit reached ({self._used}/{self._limit})"
    
    def increment_usage(self) -> bool:
        """
        Increment the usage counter.
        
        Returns:
            bool: True if increment was successful, False if limit reached
        """
        # Check if hour has changed
        self._check_and_reset_hour()
        
        if self._used >= self._limit:
            logger.warning(f"[RateLimiter] Cannot increment: limit reached ({self._used}/{self._limit})")
            return False
        
        self._used += 1
        logger.info(f"[RateLimiter] Usage incremented: {self._used - 1} → {self._used}")
        return True
    
    def get_usage(self) -> int:
        """Get current usage count."""
        self._check_and_reset_hour()
        return self._used
    
    def get_remaining(self) -> int:
        """Get remaining generations in current hour."""
        self._check_and_reset_hour()
        return max(0, self._limit - self._used)
    
    def reset_usage(self):
        """Manually reset usage counter (for testing/admin purposes)."""
        old_used = self._used
        self._used = 0
        logger.info(f"[RateLimiter] Manual reset: {old_used} → 0")


# Global singleton instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter
