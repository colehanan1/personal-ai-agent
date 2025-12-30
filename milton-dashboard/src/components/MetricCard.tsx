/**
 * MetricCard Component
 * Displays a single metric with optional icon and color accent
 */

import type { MetricCardProps } from "../types";

export function MetricCard({
  title,
  value,
  unit,
  icon,
  color = "blue",
}: MetricCardProps) {
  // Determine color classes
  const getColorClasses = (): string => {
    switch (color) {
      case "green":
        return "border-success-green/50 text-success-green";
      case "blue":
        return "border-nexus-blue/50 text-nexus-blue";
      case "purple":
        return "border-cortex-purple/50 text-cortex-purple";
      case "teal":
        return "border-frontier-teal/50 text-frontier-teal";
      case "amber":
        return "border-warning-amber/50 text-warning-amber";
      case "red":
        return "border-error-red/50 text-error-red";
      default:
        return "border-slate-500/50 text-slate-400";
    }
  };

  return (
    <div
      className={`bg-slate-800 rounded-lg p-4 border-l-4 ${getColorClasses()}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">
            {title}
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold font-mono">{value}</span>
            {unit && <span className="text-sm text-slate-400">{unit}</span>}
          </div>
        </div>

        {/* Optional icon */}
        {icon && (
          <div className="w-8 h-8 opacity-60 flex items-center justify-center">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
