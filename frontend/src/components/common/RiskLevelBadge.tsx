import type { RiskLevel } from '@/types';

const RISK_STYLES: Record<RiskLevel, string> = {
  EXTREMELY_HIGH: 'bg-ops-danger/20 text-ops-danger border-ops-danger/50',
  HIGH: 'bg-ops-danger/10 text-ops-danger border-ops-danger/30',
  MEDIUM: 'bg-ops-warning/10 text-ops-warning border-ops-warning/30',
  LOW: 'bg-ops-success/10 text-ops-success border-ops-success/30',
};

const RISK_LABELS: Record<RiskLevel, string> = {
  EXTREMELY_HIGH: 'Extremely High',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
};

export default function RiskLevelBadge({ level }: { level: RiskLevel | null | '' }) {
  if (!level) {
    return <span className="rounded-full border border-ops-border px-2 py-0.5 text-xs text-ops-textDim">Not Assessed</span>;
  }
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${RISK_STYLES[level]}`}>
      {RISK_LABELS[level]}
    </span>
  );
}
