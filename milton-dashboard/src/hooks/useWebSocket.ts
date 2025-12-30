/**
 * useWebSocket Hook
 * Manages WebSocket connection for streaming Milton responses
 */

import { useEffect, useRef, useState, useCallback } from "react";
import type { StreamMessage, UseWebSocketReturn } from "../types";

interface UseWebSocketOptions {
  url: string;
  onMessage: (message: StreamMessage) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
  onOpen?: () => void;
}

/**
 * Custom hook for managing WebSocket connections with automatic reconnection
 */
export function useWebSocket(
  options: UseWebSocketOptions
): UseWebSocketReturn {
  const { url, onMessage, onError, onClose, onOpen } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);

  // Maximum reconnect delay (30 seconds)
  const MAX_RECONNECT_DELAY = 30000;
  const BASE_RECONNECT_DELAY = 1000;

  /**
   * Calculate exponential backoff delay
   */
  const getReconnectDelay = useCallback((): number => {
    const attempts = reconnectAttemptsRef.current;
    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, attempts),
      MAX_RECONNECT_DELAY
    );
    return delay;
  }, []);

  /**
   * Close WebSocket connection
   */
  const close = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  /**
   * Connect to WebSocket
   */
  const connect = useCallback(() => {
    // Don't create duplicate connections
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
        onOpen?.();
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as StreamMessage;
          onMessage(message);
        } catch (err) {
          const parseError = new Error(
            `Failed to parse WebSocket message: ${String(err)}`
          );
          setError(parseError);
          onError?.(parseError);
        }
      };

      ws.onerror = () => {
        const wsError = new Error("WebSocket connection error");
        setError(wsError);
        onError?.(wsError);
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        wsRef.current = null;
        onClose?.();

        // Only reconnect if connection was interrupted (not normal closure)
        // Normal closure (code 1000) means stream completed successfully
        if (event.code !== 1000) {
          reconnectAttemptsRef.current += 1;
          const delay = getReconnectDelay();

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        }
      };
    } catch (err) {
      const connectError = new Error(
        `Failed to create WebSocket: ${String(err)}`
      );
      setError(connectError);
      onError?.(connectError);
    }
  }, [url, onMessage, onError, onClose, onOpen, getReconnectDelay]);

  /**
   * Connect on mount, cleanup on unmount
   */
  useEffect(() => {
    connect();

    return () => {
      close();
    };
  }, [connect, close]);

  return {
    isConnected,
    error,
    close,
  };
}
