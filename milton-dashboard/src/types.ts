/**
 * Milton Dashboard TypeScript Type Definitions
 * All interfaces for API responses, WebSocket messages, and component props
 */

// ============================================================================
// Request Types
// ============================================================================

export type AgentType = "NEXUS" | "CORTEX" | "FRONTIER";
export type RequestStatus = "PENDING" | "RUNNING" | "COMPLETE" | "FAILED";

export interface Request {
  id: string;
  query: string;
  agent?: AgentType;
  status: RequestStatus;
  timestamp: string;
  response: string;
  tokens?: number;
  duration_ms?: number;
  error?: string;
}

// ============================================================================
// WebSocket Stream Message Types
// ============================================================================

export type MessageType = "routing" | "thinking" | "token" | "memory" | "complete";

export interface BaseStreamMessage {
  type: MessageType;
  timestamp: string;
}

export interface RoutingMessage extends BaseStreamMessage {
  type: "routing";
  agent: AgentType;
  confidence: number;
  reasoning?: string;
}

export interface ThinkingMessage extends BaseStreamMessage {
  type: "thinking";
  content: string;
}

export interface TokenMessage extends BaseStreamMessage {
  type: "token";
  content: string;
}

export interface MemoryMessage extends BaseStreamMessage {
  type: "memory";
  vector_id: string;
  stored: boolean;
  embedding_size?: number;
  content?: string;
}

export interface CompleteMessage extends BaseStreamMessage {
  type: "complete";
  total_tokens: number;
  duration_ms: number;
}

export type StreamMessage =
  | RoutingMessage
  | ThinkingMessage
  | TokenMessage
  | MemoryMessage
  | CompleteMessage;

// ============================================================================
// System State Types
// ============================================================================

export type StatusType = "UP" | "DOWN" | "DEGRADED";

export interface ComponentStatus {
  status: StatusType;
  last_check: string;
}

export interface NexusStatus extends ComponentStatus {
  // Additional NEXUS-specific fields can go here
}

export interface CortexStatus extends ComponentStatus {
  running_jobs: number;
  queued_jobs: number;
}

export interface FrontierStatus extends ComponentStatus {
  // Additional FRONTIER-specific fields can go here
}

export interface MemoryStatus extends ComponentStatus {
  vector_count: number;
  memory_mb: number;
}

export interface SystemState {
  nexus: NexusStatus;
  cortex: CortexStatus;
  frontier: FrontierStatus;
  memory: MemoryStatus;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface AskResponse {
  request_id: string;
  status: string;
  agent_assigned: AgentType;
  confidence: number;
}

export interface MemoryStats {
  total_queries: number;
  vector_count: number;
  memory_size_mb: number;
  top_topics?: Array<{ topic: string; count: number }>;
}

export interface RecentRequest {
  id: string;
  query: string;
  agent: AgentType;
  timestamp: string;
  status: RequestStatus;
  duration_ms?: number;
}

// ============================================================================
// Component Prop Types
// ============================================================================

export interface RequestMessageProps {
  message: StreamMessage;
}

export interface StatusBadgeProps {
  status: StatusType;
  label: string;
  icon?: React.ReactNode;
  onClick?: () => void;
}

export interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  icon?: React.ReactNode;
  color?: "green" | "blue" | "purple" | "teal" | "amber" | "red";
}

// ============================================================================
// Hook Return Types
// ============================================================================

export interface UseWebSocketReturn {
  isConnected: boolean;
  error: Error | null;
  close: () => void;
}

export interface UseSystemStateReturn {
  state: SystemState | null;
  isLoading: boolean;
  error: Error | null;
  lastChecked: Date | null;
}

export interface UseRequestsReturn {
  requests: Request[];
  addRequest: (query: string, agent?: AgentType) => Request;
  updateRequest: (id: string, updates: Partial<Request>) => void;
  clearHistory: () => void;
  getRequest: (id: string) => Request | undefined;
}
