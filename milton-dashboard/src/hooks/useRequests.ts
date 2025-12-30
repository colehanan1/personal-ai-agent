/**
 * useRequests Hook
 * Manages request history in React state (max 20 recent requests)
 */

import { useState, useCallback } from "react";
import type { Request, AgentType, UseRequestsReturn } from "../types";

const MAX_REQUESTS = 20;

/**
 * Generate a unique request ID
 */
function generateRequestId(): string {
  return `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * Custom hook for managing request history
 */
export function useRequests(): UseRequestsReturn {
  const [requests, setRequests] = useState<Request[]>([]);

  /**
   * Add a new request to the history
   */
  const addRequest = useCallback(
    (query: string, agent?: AgentType): Request => {
      const newRequest: Request = {
        id: generateRequestId(),
        query,
        agent,
        status: "PENDING",
        timestamp: new Date().toISOString(),
        response: "",
      };

      setRequests((prev) => {
        // Add new request at the beginning
        const updated = [newRequest, ...prev];

        // Keep only the most recent MAX_REQUESTS
        return updated.slice(0, MAX_REQUESTS);
      });

      return newRequest;
    },
    []
  );

  /**
   * Update an existing request
   */
  const updateRequest = useCallback(
    (id: string, updates: Partial<Request>): void => {
      setRequests((prev) =>
        prev.map((req) => (req.id === id ? { ...req, ...updates } : req))
      );
    },
    []
  );

  /**
   * Clear all request history
   */
  const clearHistory = useCallback((): void => {
    setRequests([]);
  }, []);

  /**
   * Get a specific request by ID
   */
  const getRequest = useCallback(
    (id: string): Request | undefined => {
      return requests.find((req) => req.id === id);
    },
    [requests]
  );

  return {
    requests,
    addRequest,
    updateRequest,
    clearHistory,
    getRequest,
  };
}
