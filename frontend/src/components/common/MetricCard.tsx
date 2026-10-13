import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  badge?: {
    text: string;
    variant?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
  };
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  unit,
  subtext,
  badge,
  icon,
}) => {
  const badgeClasses = {
    neutral: 'bg-slate-800 text-slate-300 border-slate-700',
    success: 'bg-emerald-950/40 text-emerald-400 border-emerald-800/50',
    warning: 'bg-amber-950/40 text-amber-400 border-amber-800/50',
    danger: 'bg-rose-950/40 text-rose-400 border-rose-800/50',
    info: 'bg-indigo-950/40 text-indigo-400 border-indigo-800/50',
  };

  return (
    <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg shadow-sm">
      <div className="flex items-center justify-between text-xs font-medium text-slate-400 uppercase tracking-wider">
        <span>{label}</span>
        {icon && <span className="text-slate-500">{icon}</span>}
      </div>

      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="text-2xl font-bold tracking-tight text-white font-mono">
          {value}
        </span>
        {unit && <span className="text-xs text-slate-400 font-mono">{unit}</span>}
      </div>

      {(subtext || badge) && (
        <div className="mt-2.5 flex items-center justify-between gap-2 text-xs">
          {subtext && <span className="text-slate-400 truncate">{subtext}</span>}
          {badge && (
            <span
              className={`px-2 py-0.5 text-[11px] font-semibold rounded border ${badgeClasses[badge.variant || 'neutral']}`}
            >
              {badge.text}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
