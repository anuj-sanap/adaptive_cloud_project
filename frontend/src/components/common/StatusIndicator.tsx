import React from 'react';
import type { NodeStatus } from '../../types';

interface StatusIndicatorProps {
  status: NodeStatus | string;
  lastSeen?: string;
  showAge?: boolean;
}

export function formatTimeAge(isoDate?: string): string {
  if (!isoDate) return 'Never';
  const parsed = new Date(isoDate).getTime();
  if (isNaN(parsed)) return 'Invalid date';
  const diffSec = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  if (diffSec < 10) return 'Just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return `${Math.floor(diffHrs / 24)}d ago`;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  lastSeen,
  showAge = true,
}) => {
  const norm = (status || 'OFFLINE').toUpperCase();

  let dotColor = 'bg-rose-500';
  let textColor = 'text-rose-400';
  let bgColor = 'bg-rose-950/30';
  let borderColor = 'border-rose-800/40';

  if (norm === 'ONLINE') {
    dotColor = 'bg-emerald-500';
    textColor = 'text-emerald-400';
    bgColor = 'bg-emerald-950/30';
    borderColor = 'border-emerald-800/40';
  } else if (norm === 'STALE') {
    dotColor = 'bg-amber-500';
    textColor = 'text-amber-400';
    bgColor = 'bg-amber-950/30';
    borderColor = 'border-amber-800/40';
  }

  const ageText = lastSeen && showAge ? ` (${formatTimeAge(lastSeen)})` : '';

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${bgColor} ${borderColor} ${textColor}`}
      title={lastSeen ? `Last seen: ${lastSeen}` : undefined}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} aria-hidden="true" />
      <span>{norm}{ageText}</span>
    </span>
  );
};
