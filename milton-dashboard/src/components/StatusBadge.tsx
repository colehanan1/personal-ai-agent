/**
 * StatusBadge Component
 * Displays agent/service status with colored indicator
 */

import type { StatusBadgeProps } from "../types";

export function StatusBadge({ status, label, icon, onClick }: StatusBadgeProps) {
  // Determine colors based on status
  const getStatusClasses = (): string => {
    switch (status) {
      case "UP":
        return "bg-success-green/20 text-success-green border-success-green";
      case "DOWN":
        return "bg-error-red/20 text-error-red border-error-red";
      case "DEGRADED":
        return "bg-warning-amber/20 text-warning-amber border-warning-amber";
      default:
        return "bg-slate-500/20 text-slate-400 border-slate-500";
    }
  };

  const getIndicatorClasses = (): string => {
    switch (status) {
      case "UP":
        return "bg-success-green";
      case "DOWN":
        return "bg-error-red";
      case "DEGRADED":
        return "bg-warning-amber";
      default:
        return "bg-slate-500";
    }
  };

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${getStatusClasses()} ${
        onClick ? "cursor-pointer hover:brightness-110 transition-all" : ""
      }`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {/* Status indicator dot */}
      <div className={`w-2 h-2 rounded-full ${getIndicatorClasses()}`} />

      {/* Optional icon */}
      {icon && <div className="w-4 h-4">{icon}</div>}

      {/* Label */}
      <span className="text-sm font-medium">{label}</span>

      {/* Status text */}
      <span className="text-xs opacity-75">{status}</span>
    </div>
  );
}
