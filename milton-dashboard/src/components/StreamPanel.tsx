/**
 * StreamPanel Component (CENTER PANEL)
 * Displays live response streaming with auto-scroll
 */

import { useEffect, useRef, useState } from "react";
import { RequestMessage } from "./RequestMessage";
import { downloadFile, exportRequestAsJSON, exportRequestAsMarkdown } from "../api";
import type { StreamMessage, Request } from "../types";

interface StreamPanelProps {
  messages: StreamMessage[];
  currentRequest: Request | null;
  isConnected: boolean;
}

export function StreamPanel({
  messages,
  currentRequest,
  isConnected,
}: StreamPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (autoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  const handleCopyAll = () => {
    const fullResponse = messages
      .filter((m) => m.type === "token")
      .map((m) => (m.type === "token" ? m.content : ""))
      .join("");
    navigator.clipboard.writeText(fullResponse);
  };

  const handleExportJSON = () => {
    if (!currentRequest) return;
    const json = exportRequestAsJSON(currentRequest);
    downloadFile(json, `milton-stream-${currentRequest.id}.json`, "application/json");
  };

  const handleExportMarkdown = () => {
    if (!currentRequest) return;
    const markdown = exportRequestAsMarkdown(currentRequest);
    downloadFile(markdown, `milton-stream-${currentRequest.id}.md`, "text/markdown");
  };

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-slate-800 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-slate-100">
              Response Stream
            </h2>
            {isConnected && (
              <div className="flex items-center gap-2 text-xs text-success-green">
                <div className="w-2 h-2 bg-success-green rounded-full animate-pulse" />
                Connected
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyAll}
              disabled={messages.length === 0}
              className="px-3 py-1.5 bg-slate-800 text-slate-200 rounded text-xs hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Copy full response"
            >
              Copy All
            </button>
            <button
              onClick={handleExportJSON}
              disabled={!currentRequest}
              className="px-3 py-1.5 bg-slate-800 text-slate-200 rounded text-xs hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Download as JSON"
            >
              JSON
            </button>
            <button
              onClick={handleExportMarkdown}
              disabled={!currentRequest}
              className="px-3 py-1.5 bg-slate-800 text-slate-200 rounded text-xs hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Download as Markdown"
            >
              Markdown
            </button>
          </div>
        </div>
      </div>

      {/* Messages Container */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto p-4 font-mono text-sm"
      >
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-slate-500">
              <div className="text-4xl mb-4">💬</div>
              <div className="text-lg font-semibold mb-2">No active stream</div>
              <div className="text-sm">
                Send a query from the left panel to see live responses
              </div>
            </div>
          </div>
        ) : (
          <>
            {(() => {
              // Group messages: combine all consecutive tokens into one message
              const grouped: StreamMessage[] = [];
              let tokenAccumulator = "";

              messages.forEach((message, index) => {
                if (message.type === "token") {
                  tokenAccumulator += message.content;
                } else {
                  // Flush accumulated tokens before non-token message
                  if (tokenAccumulator) {
                    grouped.push({
                      type: "token",
                      content: tokenAccumulator,
                      timestamp: messages[index - 1]?.timestamp || message.timestamp,
                    });
                    tokenAccumulator = "";
                  }
                  grouped.push(message);
                }
              });

              // Flush any remaining tokens
              if (tokenAccumulator) {
                grouped.push({
                  type: "token",
                  content: tokenAccumulator,
                  timestamp: messages[messages.length - 1]?.timestamp || new Date().toISOString(),
                });
              }

              return grouped.map((message, index) => (
                <RequestMessage key={index} message={message} />
              ));
            })()}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Auto-scroll indicator */}
      {!autoScroll && messages.length > 0 && (
        <div className="absolute bottom-20 left-1/2 transform -translate-x-1/2">
          <button
            onClick={() => {
              setAutoScroll(true);
              messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            className="px-4 py-2 bg-nexus-blue text-white rounded-full shadow-lg hover:bg-nexus-blue/80 transition-all text-sm font-medium"
          >
            ↓ Scroll to bottom
          </button>
        </div>
      )}
    </div>
  );
}
