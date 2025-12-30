/**
 * Milton Dashboard - Main Application Component
 * 3-Panel Layout: Chat (left) | Stream (center) | Dashboard (right)
 */

import { useState, useCallback, useEffect } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { StreamPanel } from "./components/StreamPanel";
import { DashboardPanel } from "./components/DashboardPanel";
import { useWebSocket } from "./hooks/useWebSocket";
import { useSystemState } from "./hooks/useSystemState";
import { useRequests } from "./hooks/useRequests";
import { askMilton, getWebSocketURL } from "./api";
import type { StreamMessage, AgentType } from "./types";

export default function App() {
  const [streamMessages, setStreamMessages] = useState<StreamMessage[]>([]);
  const [currentRequestId, setCurrentRequestId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [wsUrl, setWsUrl] = useState<string>("");

  // Custom hooks
  const { requests, addRequest, updateRequest, getRequest } = useRequests();
  const { state: systemState, isLoading: systemLoading, error: systemError } = useSystemState();

  // Get current request
  const currentRequest = currentRequestId ? getRequest(currentRequestId) : null;

  // WebSocket message handler
  const handleStreamMessage = useCallback(
    (message: StreamMessage) => {
      setStreamMessages((prev) => [...prev, message]);

      // Update current request based on message type
      if (!currentRequestId) return;

      switch (message.type) {
        case "routing":
          updateRequest(currentRequestId, {
            status: "RUNNING",
            agent: message.agent,
          });
          break;

        case "token":
          updateRequest(currentRequestId, {
            response: (currentRequest?.response || "") + message.content,
          });
          break;

        case "complete":
          updateRequest(currentRequestId, {
            status: "COMPLETE",
            tokens: message.total_tokens,
            duration_ms: message.duration_ms,
          });
          break;
      }
    },
    [currentRequestId, currentRequest, updateRequest]
  );

  // WebSocket error handler
  const handleWSError = useCallback(
    (error: Error) => {
      console.error("WebSocket error:", error);
      if (currentRequestId) {
        updateRequest(currentRequestId, {
          status: "FAILED",
          error: error.message,
        });
      }
    },
    [currentRequestId, updateRequest]
  );

  // WebSocket close handler
  const handleWSClose = useCallback(() => {
    console.log("WebSocket closed");
  }, []);

  // Initialize WebSocket connection
  const { isConnected, error: wsError } = useWebSocket({
    url: wsUrl,
    onMessage: handleStreamMessage,
    onError: handleWSError,
    onClose: handleWSClose,
  });

  // Handle sending a query
  const handleSendQuery = useCallback(
    async (query: string, agent?: AgentType) => {
      setIsSending(true);
      setSendError(null);
      setStreamMessages([]);

      try {
        // Create request in history
        const request = addRequest(query, agent);
        setCurrentRequestId(request.id);

        // Send to backend API
        const response = await askMilton(query, agent);

        // Update request with backend response
        updateRequest(request.id, {
          agent: response.agent_assigned,
        });

        // Connect to WebSocket stream
        const url = getWebSocketURL(response.request_id);
        setWsUrl(url);
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : "Unknown error";
        setSendError(errorMessage);

        // Mark request as failed
        if (currentRequestId) {
          updateRequest(currentRequestId, {
            status: "FAILED",
            error: errorMessage,
          });
        }
      } finally {
        setIsSending(false);
      }
    },
    [addRequest, updateRequest, currentRequestId]
  );

  return (
    <div className="h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 bg-slate-900 border-b border-slate-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold text-slate-100">
              Milton Dashboard
            </h1>
            <div className="text-sm text-slate-400">
              3-Agent AI System Monitor
            </div>
          </div>

          {/* Global Status Indicator */}
          <div className="flex items-center gap-4">
            {systemState && (
              <div className="flex items-center gap-2 text-xs">
                {systemState.nexus.status === "UP" &&
                systemState.cortex.status === "UP" &&
                systemState.frontier.status === "UP" &&
                systemState.memory.status === "UP" ? (
                  <>
                    <div className="w-2 h-2 bg-success-green rounded-full animate-pulse" />
                    <span className="text-success-green font-medium">
                      All Systems Operational
                    </span>
                  </>
                ) : (
                  <>
                    <div className="w-2 h-2 bg-warning-amber rounded-full animate-pulse" />
                    <span className="text-warning-amber font-medium">
                      Degraded
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* 3-Panel Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT: Chat Panel (33% width) */}
        <div className="w-1/3 border-r border-slate-800 overflow-hidden">
          <ChatPanel
            requests={requests}
            onSendQuery={handleSendQuery}
            isSending={isSending}
            error={sendError}
          />
        </div>

        {/* CENTER: Stream Panel (50% width) */}
        <div className="flex-1 overflow-hidden">
          <StreamPanel
            messages={streamMessages}
            currentRequest={currentRequest}
            isConnected={isConnected}
          />
        </div>

        {/* RIGHT: Dashboard Panel (17% width) */}
        <div className="w-1/6 border-l border-slate-800 overflow-hidden">
          <DashboardPanel
            systemState={systemState}
            currentRequest={currentRequest}
            isLoading={systemLoading}
            error={systemError}
          />
        </div>
      </div>

      {/* Footer */}
      <footer className="flex-shrink-0 bg-slate-900 border-t border-slate-800 px-6 py-2">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div>
            Milton Phase 2 Dashboard • Connected to{" "}
            {import.meta.env.VITE_API_URL || "http://localhost:8001"}
          </div>
          <div>
            {wsError && (
              <span className="text-error-red">
                WebSocket Error: {wsError.message}
              </span>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}
