/**
 * Milton Dashboard API Client
 * Handles all HTTP requests to the backend at http://localhost:8001
 */

import type {
  AskResponse,
  SystemState,
  MemoryStats,
  RecentRequest,
  Request,
  AgentType,
} from "./types";

// Get API base URL from environment variables
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

/**
 * Generic fetch wrapper with error handling
 */
async function fetchJSON<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `API error: ${response.status} ${response.statusText} - ${errorText}`
      );
    }

    return await response.json();
  } catch (error) {
    if (error instanceof Error) {
      throw error;
    }
    throw new Error(`Unknown error: ${String(error)}`);
  }
}

/**
 * Send a query to Milton and get a request ID
 */
export async function askMilton(
  query: string,
  agent?: AgentType
): Promise<AskResponse> {
  return fetchJSON<AskResponse>("/api/ask", {
    method: "POST",
    body: JSON.stringify({ query, agent }),
  });
}

/**
 * Get current system state (all agents + memory)
 */
export async function getSystemState(): Promise<SystemState> {
  return fetchJSON<SystemState>("/api/system-state");
}

/**
 * Get memory statistics
 */
export async function getMemoryStats(): Promise<MemoryStats> {
  return fetchJSON<MemoryStats>("/api/memory-stats");
}

/**
 * Get recent request history
 */
export async function getRecentRequests(): Promise<RecentRequest[]> {
  return fetchJSON<RecentRequest[]>("/api/recent-requests");
}

/**
 * Get WebSocket URL for streaming responses
 */
export function getWebSocketURL(requestId: string): string {
  const wsBase = API_BASE_URL.replace("http://", "ws://").replace(
    "https://",
    "wss://"
  );
  return `${wsBase}/ws/request/${requestId}`;
}

/**
 * Export a request as JSON string
 */
export function exportRequestAsJSON(request: Request): string {
  return JSON.stringify(
    {
      id: request.id,
      query: request.query,
      agent: request.agent,
      status: request.status,
      timestamp: request.timestamp,
      response: request.response,
      tokens: request.tokens,
      duration_ms: request.duration_ms,
      error: request.error,
      exported_at: new Date().toISOString(),
    },
    null,
    2
  );
}

/**
 * Export a request as Markdown string
 */
export function exportRequestAsMarkdown(request: Request): string {
  const lines = [
    `# Milton Request: ${request.id}`,
    "",
    `**Query:** ${request.query}`,
    "",
    `**Agent:** ${request.agent || "Auto"}`,
    `**Status:** ${request.status}`,
    `**Timestamp:** ${new Date(request.timestamp).toLocaleString()}`,
  ];

  if (request.tokens) {
    lines.push(`**Tokens:** ${request.tokens}`);
  }

  if (request.duration_ms) {
    lines.push(`**Duration:** ${request.duration_ms}ms`);
  }

  if (request.error) {
    lines.push("", `**Error:** ${request.error}`);
  }

  lines.push("", "## Response", "", request.response || "(No response)");

  lines.push("", "---", `*Exported at ${new Date().toLocaleString()}*`);

  return lines.join("\n");
}

/**
 * Download a file to the user's browser
 */
export function downloadFile(
  content: string,
  filename: string,
  mimeType: string = "text/plain"
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();

  // Cleanup
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
