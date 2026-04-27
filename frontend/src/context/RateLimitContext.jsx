import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';

const RateLimitContext = createContext(null);

const STORAGE_KEY = 'rateLimit';

/** Допустимые лимиты «видео в час» — как на бэкенде (utils.rate_limiter.ALLOWED_HOURLY_LIMITS). 0 = без лимита. */
export const ALLOWED_HOURLY_LIMITS = [0, 1, 2, 3, 5, 10, 15, 30];

/** Оставшихся генераций в текущем часу; null если лимит отключён (0). */
export function remainingForLimit(limit, used) {
  if (limit === 0) return null;
  return Math.max(0, limit - used);
}

/**
 * Get current hour key in format: YYYY-MM-DD-HH
 */
function getCurrentHourKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}-${now.getHours()}`;
}

/**
 * Milliseconds until next hour boundary (HH:00:00.000)
 */
function getMsUntilNextHour() {
  const now = new Date();
  const next = new Date(now);
  next.setMinutes(60, 0, 0);
  return Math.max(0, next.getTime() - now.getTime());
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
    limit: 2,           // Default; выбор: ALLOWED_HOURLY_LIMITS
    used: 0,            // Used in current hour
    remaining: 2,       // Remaining in current hour
    hourKey: getCurrentHourKey(),
    queue: [],          // Queue of pending videos
    nextReset: null,    // Next reset time (ISO string)
    isChecking: false,  // Prevent race conditions
  }));

  const [isInitialized, setIsInitialized] = useState(false);
  const stateRef = useRef(state);
  const backendAvailableRef = useRef(true);
  const checkMutexRef = useRef(Promise.resolve());

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  /**
   * Fetch rate limit status + server-side queue.
   * localStorage is kept only as a fallback when backend is unavailable.
   */
  const fetchRateLimitStatus = useCallback(async () => {
    try {
      // Get backend status
      const backendStatus = await api.getRateLimitStatus();
      const backendQueue = await api.queueStatus();
      
      // Load from localStorage
      const stored = loadFromStorage();
      
      setState(prev => ({
        ...prev,
        limit: stored?.limit ?? backendStatus.limit,
        used: backendStatus.used,
        remaining: backendStatus.remaining,
        hourKey: backendStatus.hour_key ?? backendStatus.hourKey,
        nextReset: backendStatus.next_reset ?? backendStatus.nextReset,
        queue: backendQueue?.queue || stored?.queue || [],
      }));
      
      backendAvailableRef.current = true;
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
          remaining: remainingForLimit(stored.limit, stored.used),
          hourKey: stored.hourKey,
          queue: stored.queue || [],
        }));
      }
      backendAvailableRef.current = false;
      setIsInitialized(true);
    }
  }, []); // NO dependencies - stable function

  /**
   * Set the hourly limit (ALLOWED_HOURLY_LIMITS)
   */
  const setLimit = useCallback(async (newLimit) => {
    if (!ALLOWED_HOURLY_LIMITS.includes(newLimit)) {
      console.error('[RateLimit] Invalid limit:', newLimit);
      return false;
    }

    try {
      await api.setRateLimit(newLimit);
      
      setState(prev => {
        const newState = {
          ...prev,
          limit: newLimit,
          remaining: remainingForLimit(newLimit, prev.used),
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
    const runLocked = async () => {
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
        try {
          const res = await api.queueAdd(payload);
          const qs = await api.queueStatus().catch(() => null);
          setState(prev => ({
            ...prev,
            queue: qs?.queue ?? prev.queue,
            isChecking: false,
          }));
          return { status: 'queued', queue_item: res?.item };
        } catch {
          const q = addToQueue(payload);
          setState(prev => ({ ...prev, isChecking: false }));
          return q;
        }
      }

      // Start pipeline immediately
      try {
        const startResult = await api.startPipeline(payload);
        
        // Update usage
        setState(prev => {
        const newUsed = prev.used + 1;
        const newRemaining = remainingForLimit(prev.limit, newUsed);
        
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
          try {
            const res = await api.queueAdd(payload);
            const qs = await api.queueStatus().catch(() => null);
            if (qs?.queue) setState(prev => ({ ...prev, queue: qs.queue }));
            return { status: 'queued', queue_item: res?.item };
          } catch {
            return addToQueue(payload);
          }
        }
        
        throw pipelineError;
      }
    } catch (error) {
      setState(prev => ({ ...prev, isChecking: false }));
      throw error;
    }
    };
    const chained = checkMutexRef.current.then(runLocked, runLocked);
    checkMutexRef.current = chained.catch(() => {});
    return chained;
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
   * Add video to SERVER queue (persistent).
   * Server worker will auto-start items when allowed (including at HH:00).
   */
  const queueVideo = useCallback(async (payload) => {
    try {
      const res = await api.queueAdd(payload);
      const qs = await api.queueStatus().catch(() => null);
      if (qs?.queue) {
        setState(prev => ({ ...prev, queue: qs.queue }));
      }
      return {
        status: 'queued',
        queue_item: res?.item,
      };
    } catch (e) {
      // Fallback: local queue if server is unavailable
      return addToQueue(payload);
    }
  }, [addToQueue]);

  /**
   * Remove video from queue
   */
  const removeFromQueue = useCallback((index) => {
    const current = stateRef.current;
    const item = current.queue?.[index];
    const id = item?.id || item?.item_id;

    if (!id) {
      // fallback: local only
      setState(prev => ({ ...prev, queue: prev.queue.filter((_, i) => i !== index) }));
      return;
    }

    api.queueDelete(id)
      .then(() => api.queueStatus())
      .then((qs) => {
        if (qs?.queue) setState(prev => ({ ...prev, queue: qs.queue }));
      })
      .catch(() => {
        // fallback: local only
        setState(prev => ({ ...prev, queue: prev.queue.filter((_, i) => i !== index) }));
      });
  }, []);

  /**
   * Process queue when hour changes
   */
  const processQueue = useCallback(async () => {
    // Server is source of truth; worker handles queue starts.
    if (backendAvailableRef.current) {
      await fetchRateLimitStatus().catch(() => {});
      return;
    }

    const stored = loadFromStorage();
    const live = stateRef.current;

    const limit = stored?.limit ?? live.limit;
    let used = stored?.used ?? live.used;
    let queue = [...(stored?.queue ?? live.queue)];
    const hourKey = stored?.hourKey ?? live.hourKey;

    console.log(`[RateLimit] Starting queue processing: queue=${queue.length}, used=${used}, limit=${limit}`);

    if ((limit !== 0 && used >= limit) || queue.length === 0) {
      console.log(`[RateLimit] Queue processing skipped: used=${used}, limit=${limit}, queue=${queue.length}`);
      return;
    }

    let processedCount = 0;
    let errorCount = 0;
    const maxAttempts = limit === 0
      ? queue.length
      : Math.min(queue.length, limit - used);

    console.log(`[RateLimit] Will attempt to start ${maxAttempts} video(s) from queue`);

    for (let attempt = 0; attempt < maxAttempts && errorCount < 3; attempt++) {
      if ((limit !== 0 && used >= limit) || queue.length === 0) break;

      const item = queue[0];
      if (!item) break;

      try {
        console.log(`[RateLimit] Starting queue item #${attempt + 1}: ${item.topic} (Mode ${item.mode})`);
        await api.startPipeline(item.payload);
        queue = queue.slice(1);
        used += 1;
        processedCount++;

        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, 1500));
        }
      } catch (error) {
        console.error('[RateLimit] Failed to start queue item:', error);
        errorCount++;

        if (error?.status === 429 || error?.response?.status === 429 || error?.message?.includes('rate_limit')) {
          console.warn('[RateLimit] Queue processing stopped: rate limit reached');
          break;
        }

        if (errorCount >= 3) {
          console.error('[RateLimit] Too many errors, stopping queue processing');
          break;
        }
      }
    }

    setState(prev => ({
      ...prev,
      used,
      remaining: remainingForLimit(limit, used),
      queue,
      hourKey,
    }));

    saveToStorage({
      limit,
      hourKey,
      used,
      queue,
      lastReset: new Date().toISOString(),
    });

    console.log(`[RateLimit] Queue processing completed: started=${processedCount}, errors=${errorCount}`);
  }, [fetchRateLimitStatus]);

  /**
   * Check if hour has changed and reset if needed
   */
  const checkNewHour = useCallback(() => {
    if (backendAvailableRef.current) {
      fetchRateLimitStatus().catch(() => {});
      return;
    }

    const currentHourKey = getCurrentHourKey();
    const prevState = stateRef.current;

    if (currentHourKey === prevState.hourKey) return;

    console.log(`[RateLimit] Hour changed: ${prevState.hourKey} → ${currentHourKey}`);

    setState(prev => ({
      ...prev,
      used: 0,
      remaining: remainingForLimit(prev.limit, 0),
      hourKey: currentHourKey,
    }));

    saveToStorage({
      limit: prevState.limit,
      hourKey: currentHourKey,
      used: 0,
      queue: prevState.queue,
      lastReset: new Date().toISOString(),
    });

    setTimeout(() => {
      processQueue();
    }, 400);
  }, [processQueue, fetchRateLimitStatus]);

  /**
   * Initialize and setup polling
   */
  useEffect(() => {
    // Initial fetch
    fetchRateLimitStatus();

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps - only run on mount

  /**
   * Run hour check exactly at HH:00 and keep a fallback poll.
   * This prevents "stuck queue" when 60s interval drifts.
   */
  useEffect(() => {
    if (!isInitialized) return undefined;

    let timeoutId;

    const scheduleNextBoundaryCheck = () => {
      const delay = getMsUntilNextHour() + 200;
      timeoutId = setTimeout(() => {
        checkNewHour();
        scheduleNextBoundaryCheck();
      }, delay);
    };

    scheduleNextBoundaryCheck();
    const fallbackInterval = setInterval(checkNewHour, 30000);

    return () => {
      clearTimeout(timeoutId);
      clearInterval(fallbackInterval);
    };
  }, [isInitialized, checkNewHour]);

  // Keep UI synchronized with server queue/status.
  useEffect(() => {
    if (!isInitialized) return undefined;
    const interval = setInterval(() => {
      fetchRateLimitStatus().catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, [isInitialized, fetchRateLimitStatus]);

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
