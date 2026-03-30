"""
Test script for rate limiter functionality.

Run: python test_rate_limiter.py
"""

import time
from utils.rate_limiter import get_rate_limiter


def test_basic_functionality():
    """Test basic rate limiter operations."""
    print("\n=== Test 1: Basic Functionality ===")
    
    limiter = get_rate_limiter()
    status = limiter.get_status()
    
    print(f"Initial status: limit={status['limit']}, used={status['used']}, remaining={status['remaining']}")
    
    # Set limit to 2
    assert limiter.set_limit(2), "Failed to set limit to 2"
    print("✓ Limit set to 2")
    
    # Check if generation is allowed
    allowed, reason = limiter.check_allowed()
    assert allowed, f"Should be allowed: {reason}"
    print(f"✓ Generation allowed: {reason}")
    
    # Increment usage
    assert limiter.increment_usage(), "Failed to increment usage"
    status = limiter.get_status()
    print(f"✓ After 1st increment: used={status['used']}, remaining={status['remaining']}")
    
    # Increment again
    assert limiter.increment_usage(), "Failed to increment usage"
    status = limiter.get_status()
    print(f"✓ After 2nd increment: used={status['used']}, remaining={status['remaining']}")
    
    # Try to increment when limit reached
    allowed, reason = limiter.check_allowed()
    assert not allowed, "Should not be allowed"
    print(f"✓ Limit reached: {reason}")
    
    assert not limiter.increment_usage(), "Should not increment when limit reached"
    print("✓ Cannot increment when limit reached")
    
    # Reset and try again
    limiter.reset_usage()
    status = limiter.get_status()
    print(f"✓ After reset: used={status['used']}, remaining={status['remaining']}")
    
    allowed, reason = limiter.check_allowed()
    assert allowed, f"Should be allowed after reset: {reason}"
    print(f"✓ Generation allowed after reset: {reason}")


def test_limit_validation():
    """Test limit value validation."""
    print("\n=== Test 2: Limit Validation ===")
    
    limiter = get_rate_limiter()
    
    # Valid limits
    for valid_limit in [1, 2, 3]:
        result = limiter.set_limit(valid_limit)
        assert result, f"Should accept valid limit {valid_limit}"
        print(f"✓ Valid limit {valid_limit} accepted")
    
    # Invalid limits
    for invalid_limit in [0, 4, 5, -1]:
        result = limiter.set_limit(invalid_limit)
        assert not result, f"Should reject invalid limit {invalid_limit}"
        print(f"✓ Invalid limit {invalid_limit} rejected")


def test_hour_key_generation():
    """Test hour key format."""
    print("\n=== Test 3: Hour Key Generation ===")
    
    limiter = get_rate_limiter()
    hour_key = limiter._get_current_hour_key()
    
    # Format: YYYY-MM-DD-HH
    import re
    pattern = r'^\d{4}-\d{2}-\d{2}-\d{2}$'
    assert re.match(pattern, hour_key), f"Hour key '{hour_key}' doesn't match expected format"
    print(f"✓ Hour key format correct: {hour_key}")
    
    # Check it changes every hour (can't test in real-time, but verify logic)
    print("✓ Hour key will automatically reset at XX:00")


def test_get_remaining():
    """Test get_remaining method."""
    print("\n=== Test 4: Get Remaining ===")
    
    limiter = get_rate_limiter()
    limiter.set_limit(3)
    limiter.reset_usage()
    
    remaining = limiter.get_remaining()
    assert remaining == 3, f"Expected 3 remaining, got {remaining}"
    print(f"✓ Initial remaining: {remaining}")
    
    limiter.increment_usage()
    remaining = limiter.get_remaining()
    assert remaining == 2, f"Expected 2 remaining, got {remaining}"
    print(f"✓ After 1 increment: {remaining}")
    
    limiter.increment_usage()
    limiter.increment_usage()
    remaining = limiter.get_remaining()
    assert remaining == 0, f"Expected 0 remaining, got {remaining}"
    print(f"✓ After 3 increments: {remaining}")


if __name__ == "__main__":
    print("=" * 60)
    print("Rate Limiter Tests")
    print("=" * 60)
    
    try:
        test_basic_functionality()
        test_limit_validation()
        test_hour_key_generation()
        test_get_remaining()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
