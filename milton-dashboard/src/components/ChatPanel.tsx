/**
 * ChatPanel Component (LEFT PANEL)
 * Input queries and view request history
 */

import { useState } from "react";
import { downloadFile, exportRequestAsJSON, exportRequestAsMarkdown } from "../api";
import type { Request, AgentType } from "../types";

interface ChatPanelProps {
  requests: Request[];
  onSendQuery: (query: string, agent?: AgentType) => void;
  isSending: boolean;
  error: string | null;
}

export function ChatPanel({
  requests,
  onSendQuery,
  isSending,
  error,
}: ChatPanelProps) {
  const [query, setQuery] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<AgentType | "Auto">("Auto");
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!query.trim() || isSending) return;

    const agent = selectedAgent === "Auto" ? undefined : selectedAgent;
    onSendQuery(query.trim(), agent);
    setQuery("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case "COMPLETE":
        return "text-success-green";
      case "RUNNING":
        return "text-warning-amber";
      case "FAILED":
        return "text-error-red";
      default:
        return "text-slate-400";
    }
  };

  const getAgentColor = (agent?: string): string => {
    switch (agent) {
      case "NEXUS":
        return "bg-nexus-blue/20 text-nexus-blue border-nexus-blue";
      case "CORTEX":
        return "bg-cortex-purple/20 text-cortex-purple border-cortex-purple";
      case "FRONTIER":
        return "bg-frontier-teal/20 text-frontier-teal border-frontier-teal";
      default:
        return "bg-slate-500/20 text-slate-400 border-slate-500";
    }
  };

  const getTimeAgo = (timestamp: string): string => {
    const now = Date.now();
    const then = new Date(timestamp).getTime();
    const diffMs = now - then;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const handleExportJSON = (request: Request) => {
    const json = exportRequestAsJSON(request);
    downloadFile(json, `milton-${request.id}.json`, "application/json");
  };

  const handleExportMarkdown = (request: Request) => {
    const markdown = exportRequestAsMarkdown(request);
    downloadFile(markdown, `milton-${request.id}.md`, "text/markdown");
  };

  return (
    <div className="flex flex-col h-full bg-slate-800 p-4 gap-4">
      {/* Query Input Section */}
      <div className="flex-shrink-0">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label htmlFor="query" className="block text-sm text-slate-400 mb-2">
              Query
            </label>
            <textarea
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What papers changed this week? | Analyze this code. | Run hyperparameter sweep."
              className="w-full bg-slate-700 text-slate-100 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-nexus-blue"
              rows={3}
              disabled={isSending}
            />
            <div className="text-xs text-slate-500 mt-1">
              Press Cmd+Enter to send
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label htmlFor="agent" className="block text-sm text-slate-400 mb-2">
                Agent
              </label>
              <select
                id="agent"
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value as AgentType | "Auto")}
                className="w-full bg-slate-700 text-slate-100 rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-nexus-blue"
                disabled={isSending}
              >
                <option value="Auto">Auto (NEXUS routes)</option>
                <option value="NEXUS">NEXUS (Hub)</option>
                <option value="CORTEX">CORTEX (Executor)</option>
                <option value="FRONTIER">FRONTIER (Scout)</option>
              </select>
            </div>

            <div className="flex items-end">
              <button
                type="submit"
                disabled={!query.trim() || isSending}
                className="px-6 py-2 bg-nexus-blue text-white rounded-lg font-medium hover:bg-nexus-blue/80 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                {isSending ? (
                  <span className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Sending...
                  </span>
                ) : (
                  "Send"
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="bg-error-red/20 border border-error-red text-error-red rounded-lg p-3 text-sm">
              {error}
            </div>
          )}
        </form>
      </div>

      {/* Request History */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">
            Recent Requests
          </h3>
          <div className="text-xs text-slate-500">
            {requests.length} / 20
          </div>
        </div>

        {requests.length === 0 ? (
          <div className="text-center text-slate-500 py-8">
            No requests yet. Send a query above to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {requests.map((request) => {
              const isExpanded = expandedRequestId === request.id;

              return (
                <div key={request.id} className="bg-slate-700 rounded-lg overflow-hidden">
                  {/* Request Summary */}
                  <button
                    onClick={() => setExpandedRequestId(isExpanded ? null : request.id)}
                    className="w-full text-left p-3 hover:bg-slate-600/50 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-slate-100 font-mono truncate">
                          {request.query}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className={`text-xs px-2 py-0.5 rounded border ${getAgentColor(
                              request.agent
                            )}`}
                          >
                            {request.agent || "Auto"}
                          </span>
                          <span className="text-xs text-slate-500">
                            {getTimeAgo(request.timestamp)}
                          </span>
                        </div>
                      </div>
                      <div className={`text-sm font-medium ${getStatusColor(request.status)}`}>
                        {request.status}
                      </div>
                    </div>
                  </button>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="border-t border-slate-600 p-3 space-y-3">
                      <div>
                        <div className="text-xs text-slate-400 mb-1">Query:</div>
                        <div className="text-sm text-slate-100 font-mono whitespace-pre-wrap">
                          {request.query}
                        </div>
                      </div>

                      {request.response && (
                        <div>
                          <div className="text-xs text-slate-400 mb-1">Response:</div>
                          <div className="text-sm text-slate-100 whitespace-pre-wrap max-h-48 overflow-y-auto bg-slate-800 rounded p-2">
                            {request.response}
                          </div>
                        </div>
                      )}

                      <div className="flex items-center gap-2 text-xs text-slate-400">
                        {request.tokens && <span>Tokens: {request.tokens}</span>}
                        {request.duration_ms && (
                          <span>Duration: {(request.duration_ms / 1000).toFixed(2)}s</span>
                        )}
                      </div>

                      {request.error && (
                        <div className="bg-error-red/20 border border-error-red text-error-red rounded p-2 text-sm">
                          {request.error}
                        </div>
                      )}

                      {/* Actions */}
                      <div className="flex gap-2">
                        <button
                          onClick={() => navigator.clipboard.writeText(request.query)}
                          className="px-3 py-1 bg-slate-600 text-slate-200 rounded text-xs hover:bg-slate-500 transition-colors"
                        >
                          Copy Query
                        </button>
                        <button
                          onClick={() => handleExportJSON(request)}
                          className="px-3 py-1 bg-slate-600 text-slate-200 rounded text-xs hover:bg-slate-500 transition-colors"
                        >
                          Export JSON
                        </button>
                        <button
                          onClick={() => handleExportMarkdown(request)}
                          className="px-3 py-1 bg-slate-600 text-slate-200 rounded text-xs hover:bg-slate-500 transition-colors"
                        >
                          Export MD
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
