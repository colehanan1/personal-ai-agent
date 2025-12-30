/**
 * useSystemState Hook
 * Polls /api/system-state every 2 seconds for agent status
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { getSystemState } from "../api";
import type { SystemState, UseSystemStateReturn } from "../types";

const POLL_INTERVAL_MS = 2000; // 2 seconds

/**
 * Custom hook for polling system state
 */
export function useSystemState(): UseSystemStateReturn {
  const [state, setState] = useState<SystemState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);

  /**
   * Fetch system state from API
   */
  const fetchState = useCallback(async () => {
    try {
      const newState = await getSystemState();

      if (isMountedRef.current) {
        setState(newState);
        setError(null);
        setIsLoading(false);
        setLastChecked(new Date());
      }
    } catch (err) {
      if (isMountedRef.current) {
        const fetchError =
          err instanceof Error ? err : new Error(String(err));
        setError(fetchError);
        setIsLoading(false);
      }
    }
  }, []);

  /**
   * Start polling on mount
   */
  useEffect(() => {
    isMountedRef.current = true;

    // Fetch immediately
    fetchState();

    // Then poll every 2 seconds
    intervalRef.current = setInterval(() => {
      fetchState();
    }, POLL_INTERVAL_MS);

    // Cleanup on unmount
    return () => {
      isMountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchState]);

  return {
    state,
    isLoading,
    error,
    lastChecked,
  };
}
