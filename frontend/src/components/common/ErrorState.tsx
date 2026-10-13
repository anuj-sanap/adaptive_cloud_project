import React from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  statusCode?: number;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Failed to load telemetry',
  message,
  onRetry,
  statusCode,
}) => {
  return (
    <div
      role="alert"
      className="p-6 bg-rose-950/20 border border-rose-900/50 rounded-lg text-slate-200"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-rose-300">{title}</h4>
            {statusCode ? (
              <span className="text-xs px-2 py-0.5 bg-rose-900/40 text-rose-300 rounded border border-rose-800/60 font-mono">
                HTTP {statusCode}
              </span>
            ) : null}
          </div>
          <p className="text-sm text-slate-300 mt-1 break-words">{message}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-rose-200 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-800 rounded transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry Request
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
