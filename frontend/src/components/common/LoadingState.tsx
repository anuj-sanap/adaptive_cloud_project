import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  message?: string;
  subtext?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading telemetry data...',
  subtext = 'Connecting to central API...',
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center p-12 text-center bg-slate-900/50 border border-slate-800 rounded-lg"
    >
      <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mb-3" aria-hidden="true" />
      <p className="text-sm font-medium text-slate-200">{message}</p>
      {subtext && <p className="text-xs text-slate-400 mt-1">{subtext}</p>}
    </div>
  );
};
