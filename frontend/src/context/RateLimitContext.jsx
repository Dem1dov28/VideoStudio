import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';

const RateLimitContext = createContext(null);

const STORAGE_KEY = 'rateLimit';

/**
 * Get current hour key in format: YYYY-MM-DD-HH
 */
function getCurrentHourKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}-${now.getHours()}`;
}

/**
 * Load rate limit data from localStorage
 */
function loadFromStorage() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return null;
    
    const parsed = JSON.parse(data);
    
    // Check if hour has changed
    const currentHourKey = getCurrentHourKey();
    if (parsed.hourKey !== currentHourKey) {
      // New hour - reset usage
      parsed.used = 0;
      parsed.hourKey = currentHourKey;
      parsed.lastReset = new Date().toISOString();
      saveToStorage(parsed);
    }
    
    return parsed;
  } catch (error) {
    console.error('[RateLimit] Failed to load from storage:', error);
    return null;
  }
}

/**
 * Save rate limit data to localStorage
 */
function saveToStorage(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (error) {
    console.error('[RateLimit] Failed to save to storage:', error);
  }
}

export function RateLimitProvider({ children }) {
  const [state, setState] = useState(() => ({
    limit: 2,           // Default limit (1-3)
    used: 0,            // Used in current hour
    remaining: 2,       // Remaining in current hour
    hourKey: getCurrentHourKey(),
    queue: [],          // Queue of pending videos
    nextReset: null,    // Next reset time (ISO string)
    isChecking: false,  // Prevent race conditions
  }));

  const [isInitialized, setIsInitialized] = useState(false);

  /**
   * Fetch rate limit status from backend and initialize from localStorage
   */
  const fetchRateLimitStatus = useCallback(async () => {
    try {
      // Get backend status
      const backendStatus = await api.getRateLimitStatus();
      
      // Load from localStorage
      const stored = loadFromStorage();
      
      setState(prev => ({
        ...prev,
        limit: stored?.limit ?? backendStatus.limit,
        used: backendStatus.used,
        remaining: backendStatus.remaining,
        hourKey: backendStatus.hourKey,
        nextReset: backendStatus.next_reset,
        queue: stored?.queue || [],
      }));
      
      setIsInitialized(true);
    } catch (error) {
      // Network error - server unavailable, use localStorage only
      console.warn('[RateLimit] Backend unavailable, using localStorage fallback');
      const stored = loadFromStorage();
      if (stored) {
        setState(prev => ({
          ...prev,
          limit: stored.limit,
          used: stored.used,
          remaining: Math.max(0, stored.limit - stored.used),
          hourKey: stored.hourKey,
          queue: stored.queue || [],
        }));
      }
      setIsInitialized(true);
    }
  }, []); // NO dependencies - stable function

  /**
   * Set the hourly limit (1-3)
   */
  const setLimit = useCallback(async (newLimit) => {
    if (![1, 2, 3].includes(newLimit)) {
      console.error('[RateLimit] Invalid limit:', newLimit);
      return false;
    }

    try {
      await api.setRateLimit(newLimit);
      
      setState(prev => {
        const newState = {
          ...prev,
          limit: newLimit,
          remaining: Math.max(0, newLimit - prev.used),
        };
        
        // Save to localStorage
        saveToStorage({
          limit: newLimit,
          hourKey: newState.hourKey,
          used: prev.used,
          queue: prev.queue,
          lastReset: new Date().toISOString(),
        });
        
        return newState;
      });
      
      return true;
    } catch (error) {
      console.error('[RateLimit] Failed to set limit:', error);
      return false;
    }
  }, []);

  /**
   * Check if video generation is allowed and start it or add to queue
   */
  const checkAndStartVideo = useCallback(async (payload) => {
    if (state.isChecking) {
      // Wait for current check to complete
      await new Promise(resolve => setTimeout(resolve, 500));
      return checkAndStartVideo(payload);
    }

    setState(prev => ({ ...prev, isChecking: true }));

    try {
      // Check rate limit
      const checkResult = await api.checkRateLimit();
      
      if (!checkResult.allowed) {
        // Limit reached - add to queue
        return addToQueue(payload);
      }

      // Start pipeline immediately
      try {
        const startResult = await api.startPipeline(payload);
        
        // Update usage
        setState(prev => {
        const newUsed = prev.used + 1;
        const newRemaining = prev.limit - newUsed;
        
        const newState = {
          ...prev,
          used: newUsed,
          remaining: newRemaining,
          isChecking: false,
        };
        
        // Save to localStorage
        saveToStorage({
          limit: prev.limit,
          hourKey: prev.hourKey,
          used: newUsed,
          queue: prev.queue,
          lastReset: new Date().toISOString(),
        });
        
        return newState;
      });
      
      return {
        status: 'started',
        session_id: startResult.session_id,
      };
      } catch (pipelineError) {
        setState(prev => ({ ...prev, isChecking: false }));
        
        // Check if it's a rate limit error (429)
        if (pipelineError.response?.status === 429 || pipelineError.message?.includes('rate_limit')) {
          // Hour changed or race condition - add to queue
          console.warn('[RateLimit] Race condition detected, adding to queue');
          return addToQueue(payload);
        }
        
        throw pipelineError;
      }
    } catch (error) {
      setState(prev => ({ ...prev, isChecking: false }));
      throw error;
    }
  }, [state.isChecking, state.limit, state.used]);

  /**
   * Add video to queue
   */
  const addToQueue = useCallback((payload) => {
    const queueItem = {
      id: Date.now(),
      topic: payload.topic || `Видео #${Date.now()}`,
      mode: payload.mode || 1,
      timestamp: Date.now(),
      payload: { ...payload },
    };

    setState(prev => {
      const newQueue = [...prev.queue, queueItem];
      
      // Save to localStorage
      saveToStorage({
        limit: prev.limit,
        hourKey: prev.hourKey,
        used: prev.used,
        queue: newQueue,
        lastReset: new Date().toISOString(),
      });
      
      return {
        ...prev,
        queue: newQueue,
      };
    });

    return {
      status: 'queued',
      queue_item: queueItem,
    };
  }, []);

  /**
   * Add video to queue and try to start immediately if limit available
   */
  const queueVideo = useCallback(async (payload) => {
    const queueItem = {
      id: Date.now(),
      topic: payload.topic || `Видео #${Date.now()}`,
      mode: payload.mode || 1,
      timestamp: Date.now(),
      payload: { ...payload },
    };

    // First, check if we can start immediately
    const hasAvailableSlots = state.used < state.limit;
    
    if (hasAvailableSlots) {
      console.log(`[RateLimit] queueVideo: available slots detected (used=${state.used}, limit=${state.limit}), starting immediately`);
      
      try {
        // Try to start immediately
        const startResult = await api.startPipeline(payload);
        
        // Update usage
        setState(prev => {
          const newUsed = prev.used + 1;
          const newRemaining = prev.limit - newUsed;
          
          const newState = {
            ...prev,
            used: newUsed,
            remaining: newRemaining,
          };
          
          saveToStorage({
            limit: prev.limit,
            hourKey: prev.hourKey,
            used: newUsed,
            queue: prev.queue,
            lastReset: new Date().toISOString(),
          });
          
          return newState;
        });
        
        console.log(`[RateLimit] Started immediately: session=${startResult.session_id}`);
        
        return {
          status: 'started',
          session_id: startResult.session_id,
        };
      } catch (error) {
        console.error('[RateLimit] Failed to start immediately, adding to queue:', error);
        // If failed, add to queue anyway
      }
    }
    
    // No available slots or start failed - add to queue
    console.log(`[RateLimit] queueVideo: adding to queue (used=${state.used}, limit=${state.limit})`);
    
    setState(prev => {
      const newQueue = [...prev.queue, queueItem];
      
      saveToStorage({
        limit: prev.limit,
        hourKey: prev.hourKey,
        used: prev.used,
        queue: newQueue,
        lastReset: new Date().toISOString(),
      });
      
      return {
        ...prev,
        queue: newQueue,
      };
    });

    return {
      status: 'queued',
      queue_item: queueItem,
    };
  }, [state.used, state.limit]);

  /**
   * Remove video from queue
   */
  const removeFromQueue = useCallback((index) => {
    setState(prev => {
      const newQueue = prev.queue.filter((_, i) => i !== index);
      
      // Save to localStorage
      saveToStorage({
        limit: prev.limit,
        hourKey: prev.hourKey,
        used: prev.used,
        queue: newQueue,
        lastReset: new Date().toISOString(),
      });
      
      return {
        ...prev,
        queue: newQueue,
      };
    });
  }, []);

  /**
   * Process queue when hour changes
   */
  const processQueue = useCallback(async () => {
    console.log(`[RateLimit] Starting queue processing: queue=${state.queue.length}, used=${state.used}, limit=${state.limit}`);
    
    // Check if we have available slots and items in queue
    const hasAvailableSlots = state.used < state.limit;
    const hasQueueItems = state.queue.length > 0;
    
    if (!hasAvailableSlots || !hasQueueItems) {
      console.log(`[RateLimit] Queue processing skipped: used=${state.used}, limit=${state.limit}, queue=${state.queue.length}`);
      return;
    }

    // Process videos one by one until limit reached or queue empty
    let processedCount = 0;
    let errorCount = 0;
    const maxAttempts = Math.min(state.queue.length, state.limit - state.used);
    
    console.log(`[RateLimit] Will attempt to start ${maxAttempts} video(s) from queue`);

    for (let attempt = 0; attempt < maxAttempts && errorCount < 3; attempt++) {
      // Get current state (not snapshot!) to check remaining slots
      const currentState = loadFromStorage();
      const currentUsed = currentState?.used ?? state.used;
      const currentLimit = currentState?.limit ?? state.limit;
      
      if (currentUsed >= currentLimit) {
        console.log(`[RateLimit] Queue processing stopped: limit reached (${currentUsed}/${currentLimit})`);
        break;
      }
      
      // Get first item from queue (always index 0 since we remove after each success)
      const queue = loadFromStorage()?.queue || [];
      if (queue.length === 0) {
        console.log(`[RateLimit] Queue processing stopped: queue is empty`);
        break;
      }
      
      const item = queue[0]; // Always take first item
      if (!item) continue;

      try {
        console.log(`[RateLimit] Starting queue item #${attempt + 1}: ${item.topic} (Mode ${item.mode})`);
        
        // Start the pipeline
        const startResult = await api.startPipeline(item.payload);
        
        // Update usage and remove from queue
        setState(prev => {
          const newUsed = prev.used + 1;
          const newRemaining = prev.limit - newUsed;
          
          // Remove FIRST item from queue (index 0)
          const newQueue = prev.queue.filter((_, idx) => idx !== 0);
          
          const newState = {
            ...prev,
            used: newUsed,
            remaining: newRemaining,
            queue: newQueue,
          };
          
          // Save to localStorage
          saveToStorage({
            limit: prev.limit,
            hourKey: prev.hourKey,
            used: newUsed,
            queue: newQueue,
            lastReset: new Date().toISOString(),
          });
          
          console.log(`[RateLimit] Started successfully: used=${newUsed}, remaining=${newRemaining}, queue_left=${newQueue.length}`);
          return newState;
        });
        
        processedCount++;
        
        // Wait a bit between starts to avoid race conditions
        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
        
      } catch (error) {
        console.error(`[RateLimit] Failed to start queue item:`, error);
        errorCount++;
        
        // Check if it's a rate limit error - if so, stop processing
        if (error.response?.status === 429 || error.message?.includes('rate_limit')) {
          console.warn('[RateLimit] Queue processing stopped: rate limit reached');
          // Don't remove from queue - will retry next hour
          return; // Stop processing more items
        }
        
        // Other errors - leave in queue and continue to next
        if (errorCount >= 3) {
          console.error('[RateLimit] Too many errors, stopping queue processing');
          return;
        }
      }
    }
    
    console.log(`[RateLimit] Queue processing completed: started=${processedCount}, errors=${errorCount}`);
  }, [state.queue, state.limit, state.used, state.remaining]);

  /**
   * Check if hour has changed and reset if needed
   */
  const checkNewHour = useCallback(() => {
    const currentHourKey = getCurrentHourKey();
    
    // Check locally first (no API call)
    if (currentHourKey !== state.hourKey) {
      console.log(`[RateLimit] Hour changed: ${state.hourKey} → ${currentHourKey}`);
      
      // Reset usage
      setState(prev => ({
        ...prev,
        used: 0,
        remaining: prev.limit,
        hourKey: currentHourKey,
      }));
      
      // Save to localStorage
      saveToStorage({
        limit: state.limit,
        hourKey: currentHourKey,
        used: 0,
        queue: state.queue,
        lastReset: new Date().toISOString(),
      });
      
      // Process queue automatically after 1 second
      setTimeout(() => processQueue(), 1000);
      
      // DO NOT call fetchRateLimitStatus here - it causes infinite loop!
      // The state update above is sufficient
    }
    // If hour hasn't changed, do nothing (no API call)
  }, [state.hourKey, state.limit, state.queue, processQueue]);

  /**
   * Initialize and setup polling
   */
  useEffect(() => {
    // Initial fetch
    fetchRateLimitStatus();
    
    // Poll every 60 seconds to check for hour change
    const interval = setInterval(() => {
      checkNewHour();
    }, 60000); // 60 seconds
    
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps - only run on mount

  const value = {
    ...state,
    setLimit,
    checkAndStartVideo,
    addToQueue,
    queueVideo, // Always add to queue
    removeFromQueue,
    processQueue,
    fetchRateLimitStatus,
    isInitialized,
  };

  return (
    <RateLimitContext.Provider value={value}>
      {children}
    </RateLimitContext.Provider>
  );
}

export function useRateLimit() {
  const context = useContext(RateLimitContext);
  if (!context) {
    throw new Error('useRateLimit must be used within RateLimitProvider');
  }
  return context;
}
