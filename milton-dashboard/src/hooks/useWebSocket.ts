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
  const manualCloseRef = useRef(false);
  const urlRef = useRef(url);
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const onCloseRef = useRef(onClose);
  const onOpenRef = useRef(onOpen);

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
    manualCloseRef.current = true;
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
    // Don't connect if URL is empty
    if (!url) {
      return;
    }

    // Don't create duplicate connections
    if (
      wsRef.current &&
      wsRef.current.readyState !== WebSocket.CLOSED
    ) {
      return;
    }

    try {
      manualCloseRef.current = false;
      const connectionUrl = url;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
        onOpenRef.current?.();
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as StreamMessage;
          onMessageRef.current(message);
        } catch (err) {
          const parseError = new Error(
            `Failed to parse WebSocket message: ${String(err)}`
          );
          setError(parseError);
          onErrorRef.current?.(parseError);
        }
      };

      ws.onerror = () => {
        if (manualCloseRef.current || wsRef.current !== ws) {
          return;
        }
        const wsError = new Error("WebSocket connection error");
        setError(wsError);
        onErrorRef.current?.(wsError);
      };

      ws.onclose = (event) => {
        const wasManualClose = manualCloseRef.current;
        manualCloseRef.current = false;
        setIsConnected(false);
        wsRef.current = null;
        onCloseRef.current?.();

        if (wasManualClose) {
          return;
        }

        if (!urlRef.current || urlRef.current !== connectionUrl) {
          return;
        }

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
      onErrorRef.current?.(connectError);
    }
  }, [url, getReconnectDelay]);

  useEffect(() => {
    urlRef.current = url;
  }, [url]);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

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
