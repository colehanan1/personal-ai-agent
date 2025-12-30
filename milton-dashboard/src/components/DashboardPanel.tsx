/**
 * DashboardPanel Component (RIGHT PANEL)
 * System health monitoring and metrics
 */

import { StatusBadge } from "./StatusBadge";
import { MetricCard } from "./MetricCard";
import type { SystemState, Request } from "../types";

interface DashboardPanelProps {
  systemState: SystemState | null;
  currentRequest: Request | null;
  isLoading: boolean;
  error: Error | null;
}

export function DashboardPanel({
  systemState,
  currentRequest,
  isLoading,
  error,
}: DashboardPanelProps) {
  const formatNumber = (num: number): string => {
    return new Intl.NumberFormat("en-US").format(num);
  };


  return (
    <div className="flex flex-col h-full bg-slate-900 p-4 gap-4 overflow-y-auto">
      {/* System Status Section */}
      <div>
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
          System Status
        </h3>

        {isLoading && !systemState ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <div className="w-4 h-4 border-2 border-slate-500/30 border-t-slate-500 rounded-full animate-spin" />
            Loading...
          </div>
        ) : error ? (
          <div className="bg-error-red/20 border border-error-red text-error-red rounded-lg p-3 text-xs">
            {error.message}
          </div>
        ) : systemState ? (
          <div className="space-y-2">
            <StatusBadge
              status={systemState.nexus.status}
              label="NEXUS"
              icon={
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M10 2a8 8 0 100 16 8 8 0 000-16zM8 11a1 1 0 112 0 1 1 0 01-2 0zm3-1a1 1 0 100 2 1 1 0 000-2z" />
                </svg>
              }
            />

            <StatusBadge
              status={systemState.cortex.status}
              label="CORTEX"
              icon={
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z" />
                </svg>
              }
            />

            <StatusBadge
              status={systemState.frontier.status}
              label="FRONTIER"
              icon={
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
                  <path
                    fillRule="evenodd"
                    d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z"
                    clipRule="evenodd"
                  />
                </svg>
              }
            />

            <StatusBadge
              status={systemState.memory.status}
              label="Memory"
              icon={
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
                  <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
                  <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
                </svg>
              }
            />
          </div>
        ) : null}
      </div>

      {/* Current Request Metrics */}
      {currentRequest && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
            Current Request
          </h3>
          <div className="space-y-2">
            <MetricCard
              title="Agent"
              value={currentRequest.agent || "Auto"}
              color={
                currentRequest.agent === "NEXUS"
                  ? "blue"
                  : currentRequest.agent === "CORTEX"
                  ? "purple"
                  : currentRequest.agent === "FRONTIER"
                  ? "teal"
                  : "blue"
              }
            />

            <MetricCard
              title="Status"
              value={currentRequest.status}
              color={
                currentRequest.status === "COMPLETE"
                  ? "green"
                  : currentRequest.status === "RUNNING"
                  ? "amber"
                  : currentRequest.status === "FAILED"
                  ? "red"
                  : "blue"
              }
            />

            {currentRequest.tokens && (
              <MetricCard
                title="Tokens Used"
                value={currentRequest.tokens}
                unit="tokens"
                color="green"
              />
            )}

            {currentRequest.duration_ms && (
              <MetricCard
                title="Duration"
                value={(currentRequest.duration_ms / 1000).toFixed(2)}
                unit="seconds"
                color="teal"
              />
            )}
          </div>
        </div>
      )}

      {/* Memory Snapshot */}
      {systemState?.memory && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
            Memory Snapshot
          </h3>
          <div className="space-y-2">
            <MetricCard
              title="Vectors Stored"
              value={formatNumber(systemState.memory.vector_count)}
              color="purple"
              icon={
                <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
                  <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
                </svg>
              }
            />

            <MetricCard
              title="Memory Size"
              value={systemState.memory.memory_mb.toFixed(1)}
              unit="MB"
              color="purple"
              icon={
                <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M3 5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-2.22l.123.489.804.804A1 1 0 0113 18H7a1 1 0 01-.707-1.707l.804-.804L7.22 15H5a2 2 0 01-2-2V5zm5.771 7H5V5h10v7H8.771z"
                    clipRule="evenodd"
                  />
                </svg>
              }
            />
          </div>
        </div>
      )}

      {/* CORTEX Queue Status */}
      {systemState?.cortex && (
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
            CORTEX Queue
          </h3>
          <div className="space-y-2">
            <MetricCard
              title="Running Jobs"
              value={systemState.cortex.running_jobs}
              color={systemState.cortex.running_jobs > 0 ? "amber" : "green"}
            />

            <MetricCard
              title="Queued Jobs"
              value={systemState.cortex.queued_jobs}
              color={systemState.cortex.queued_jobs > 0 ? "blue" : "green"}
            />
          </div>

          {systemState.cortex.queued_jobs === 0 &&
            systemState.cortex.running_jobs === 0 && (
              <div className="mt-2 text-xs text-slate-500 text-center">
                No active jobs
              </div>
            )}
        </div>
      )}

      {/* Last Updated */}
      {systemState && (
        <div className="mt-auto pt-4 border-t border-slate-800">
          <div className="text-xs text-slate-500 text-center">
            Last updated:{" "}
            {new Date(systemState.nexus.last_check).toLocaleTimeString()}
          </div>
        </div>
      )}
    </div>
  );
}
