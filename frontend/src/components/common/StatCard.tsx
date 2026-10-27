import React from 'react';

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  accent?: 'default' | 'danger' | 'warning' | 'success';
  subtext?: string;
}

const accentClasses: Record<NonNullable<StatCardProps['accent']>, string> = {
  default: 'text-ops-accent border-ops-accent/30',
  danger: 'text-ops-danger border-ops-danger/30',
  warning: 'text-ops-warning border-ops-warning/30',
  success: 'text-ops-success border-ops-success/30',
};

export default function StatCard({ label, value, icon, accent = 'default', subtext }: StatCardProps) {
  return (
    <div className="ops-card flex items-center justify-between p-4">
      <div>
        <p className="ops-label">{label}</p>
        <p className={`mt-1 font-mono text-3xl font-bold ${accentClasses[accent].split(' ')[0]}`}>{value}</p>
        {subtext && <p className="mt-1 text-xs text-ops-textDim">{subtext}</p>}
      </div>
      {icon && (
        <div className={`flex h-12 w-12 items-center justify-center rounded-md border bg-ops-panelLight ${accentClasses[accent]}`}>
          {icon}
        </div>
      )}
    </div>
  );
}
