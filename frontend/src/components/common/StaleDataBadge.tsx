import React from 'react';
import { Clock } from 'lucide-react';
import { formatTimeAge } from './StatusIndicator';

interface StaleDataBadgeProps {
  timestamp?: string;
  maxAgeSeconds?: number;
}

export const StaleDataBadge: React.FC<StaleDataBadgeProps> = ({
  timestamp,
  maxAgeSeconds = 30,
}) => {
  if (!timestamp) return null;
  const parsed = new Date(timestamp).getTime();
  if (isNaN(parsed)) return null;

  const diffSec = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  const isStale = diffSec > maxAgeSeconds;

  if (!isStale) return null;

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-amber-300 bg-amber-950/40 border border-amber-800/50 rounded"
      title={`Telemetry timestamp: ${timestamp} (${diffSec}s old)`}
    >
      <Clock className="w-3 h-3 text-amber-400" aria-hidden="true" />
      <span>Delayed · {formatTimeAge(timestamp)}</span>
    </span>
  );
};
