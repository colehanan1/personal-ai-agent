/**
 * RequestMessage Component
 * Displays a single stream message with type-specific styling
 */

import type { RequestMessageProps } from "../types";

export function RequestMessage({ message }: RequestMessageProps) {
  const { type, timestamp } = message;

  // Format timestamp
  const time = new Date(timestamp).toLocaleTimeString();

  // Get icon and styling based on message type
  const getMessageStyles = () => {
    switch (type) {
      case "routing":
        return {
          icon: "✓",
          borderColor: "border-warning-amber",
          bgColor: "bg-warning-amber/10",
          textColor: "text-warning-amber",
        };
      case "thinking":
        return {
          icon: "🧠",
          borderColor: "border-nexus-blue",
          bgColor: "bg-nexus-blue/10",
          textColor: "text-nexus-blue",
        };
      case "token":
        return {
          icon: "▶",
          borderColor: "border-success-green",
          bgColor: "bg-success-green/10",
          textColor: "text-success-green",
        };
      case "memory":
        return {
          icon: "💾",
          borderColor: "border-cortex-purple",
          bgColor: "bg-cortex-purple/10",
          textColor: "text-cortex-purple",
        };
      case "complete":
        return {
          icon: "✓",
          borderColor: "border-frontier-teal",
          bgColor: "bg-frontier-teal/10",
          textColor: "text-frontier-teal",
        };
    }
  };

  const styles = getMessageStyles();

  // Render content based on message type
  const renderContent = () => {
    switch (message.type) {
      case "routing":
        return (
          <>
            <div className="font-semibold">NEXUS received query</div>
            <div className="text-sm opacity-90">
              → Routing to: <span className="font-bold">{message.agent}</span>
            </div>
            <div className="text-sm opacity-90">
              → Confidence: {(message.confidence * 100).toFixed(1)}%
            </div>
            {message.reasoning && (
              <div className="text-sm opacity-75 mt-1">
                → {message.reasoning}
              </div>
            )}
          </>
        );

      case "thinking":
        return (
          <>
            <div className="font-semibold">Agent thinking...</div>
            <div className="text-sm opacity-90 italic">{message.content}</div>
          </>
        );

      case "token":
        return <div className="whitespace-pre-wrap">{message.content}</div>;

      case "memory":
        return (
          <>
            <div className="font-semibold">Storing in Weaviate</div>
            <div className="text-sm opacity-90">
              → Vector ID: <span className="font-mono">{message.vector_id}</span>
            </div>
            {message.embedding_size && (
              <div className="text-sm opacity-90">
                → Embedding: {message.embedding_size}d
              </div>
            )}
            <div className="text-sm opacity-90">
              → Stored: {message.stored ? "✓ Yes" : "✗ Failed"}
            </div>
          </>
        );

      case "complete":
        return (
          <>
            <div className="font-semibold">Response complete</div>
            <div className="text-sm opacity-90">
              → Tokens: {message.total_tokens}
            </div>
            <div className="text-sm opacity-90">
              → Duration: {(message.duration_ms / 1000).toFixed(2)}s
            </div>
          </>
        );
    }
  };

  return (
    <div
      className={`border-l-4 ${styles.borderColor} ${styles.bgColor} rounded-r-lg p-3 mb-2`}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className={`text-lg ${styles.textColor} flex-shrink-0`}>
          {styles.icon}
        </div>

        {/* Content */}
        <div className={`flex-1 ${styles.textColor}`}>{renderContent()}</div>

        {/* Timestamp */}
        <div className="text-xs text-slate-500 flex-shrink-0">{time}</div>
      </div>
    </div>
  );
}
