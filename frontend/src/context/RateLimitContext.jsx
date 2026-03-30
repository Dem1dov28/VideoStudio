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
      console.error('[RateLimit] Failed to fetch status:', error);
      // Use localStorage fallback
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
  }, []);

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
    setState(prev => {
      if (prev.queue.length === 0 || prev.remaining >= prev.limit) {
        return prev;
      }
      return prev;
    });

    const stateSnapshot = state;
    const canStart = Math.min(
      stateSnapshot.queue.length,
      stateSnapshot.limit - stateSnapshot.used
    );

    if (canStart <= 0) return;

    // Process first N items in queue
    for (let i = 0; i < canStart; i++) {
      const item = stateSnapshot.queue[i];
      if (!item) continue;

      try {
        // Start the pipeline
        const startResult = await api.startPipeline(item.payload);
        
        // Update usage
        setState(prev => {
          const newUsed = prev.used + 1;
          const newRemaining = prev.limit - newUsed;
          
          // Remove from queue
          const newQueue = prev.queue.filter((_, idx) => idx !== i);
          
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
          
          return newState;
        });
        
        console.log(`[RateLimit] Queue item started: ${item.topic}, session: ${startResult.session_id}`);
      } catch (error) {
        console.error(`[RateLimit] Failed to start queue item:`, error);
        
        // Check if it's a rate limit error - if so, stop processing
        if (error.response?.status === 429 || error.message?.includes('rate_limit')) {
          console.warn('[RateLimit] Queue processing stopped: rate limit reached');
          // Don't remove from queue - will retry next hour
          return; // Stop processing more items
        }
        
        // Other errors - leave in queue and continue
      }
    }
  }, [state.queue, state.limit, state.used, state.remaining]);

  /**
   * Check if hour has changed and reset if needed
   */
  const checkNewHour = useCallback(() => {
    const currentHourKey = getCurrentHourKey();
    const stored = loadFromStorage();
    
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
      
      // Process queue automatically
      setTimeout(() => processQueue(), 1000);
      
      // Sync with backend
      fetchRateLimitStatus();
    }
  }, [state.hourKey, state.limit, state.queue, processQueue, fetchRateLimitStatus]);

  /**
   * Initialize and setup polling
   */
  useEffect(() => {
    // Initial fetch
    fetchRateLimitStatus();
    
    // Poll every 10 seconds to check for hour change
    const interval = setInterval(() => {
      checkNewHour();
    }, 10000);
    
    return () => clearInterval(interval);
  }, [fetchRateLimitStatus, checkNewHour]);

  const value = {
    ...state,
    setLimit,
    checkAndStartVideo,
    addToQueue,
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
