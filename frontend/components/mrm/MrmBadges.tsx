import type { MrmStage, RiskTier } from '@/types/mrm';

const LEVEL_STYLE: Record<RiskTier, string> = {
  HIGH: 'bg-red-500/90 text-white',
  MEDIUM: 'bg-yellow-400 text-black',
  LOW: 'bg-green-600 text-white',
};

/** A single risk-matrix cell such as "4B", coloured by the official matrix. */
export function RiskCell({ rating, level }: { rating: string; level: RiskTier }) {
  return (
    <span className={`inline-block min-w-[2.5rem] rounded px-2 py-0.5 text-center font-mono text-xs font-bold ${LEVEL_STYLE[level]}`}>
      {rating}
    </span>
  );
}

const STAGE: Record<MrmStage, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-ops-textDim/10 text-ops-textDim' },
  awaiting_review: { label: 'Awaiting review', className: 'bg-ops-warning/10 text-ops-warning' },
  needs_revision: { label: 'Needs revision', className: 'bg-orange-500/10 text-orange-400' },
  rejected: { label: 'Rejected', className: 'bg-ops-danger/10 text-ops-danger' },
  awaiting_authority: { label: 'Awaiting approval', className: 'bg-ops-accent/10 text-ops-accent' },
  needs_authority_assignment: { label: 'Needs approver', className: 'bg-ops-danger/10 text-ops-danger' },
  approved: { label: 'Approved', className: 'bg-ops-success/10 text-ops-success' },
};

export function StageBadge({ stage }: { stage: MrmStage }) {
  const s = STAGE[stage] ?? STAGE.draft;
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.className}`}>{s.label}</span>;
}

export function PercentBar({ percent }: { percent: number }) {
  const color = percent <= 50 ? 'bg-green-600' : percent <= 75 ? 'bg-yellow-400' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-ops-panelLight">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
      <span className="font-mono text-xs text-ops-text">{percent.toFixed(0)}%</span>
    </div>
  );
}

export const AUTHORITY_LABEL: Record<string, string> = {
  ADMINISTRATOR: 'Administrator',
  EVALUATOR: 'Evaluator',
  CREATOR: 'Creator',
  UNIT_SAFETY_OFFICER: 'Unit Safety Officer',
};

export const DESIGNATION_OPTIONS = [
  { value: 'OPERATOR', label: 'Operator (≤50%)' },
  { value: 'SUPERVISOR', label: 'Supervisor (51–65%)' },
  { value: 'SQUADRON_COMMANDER', label: 'Squadron Commander (66–75%)' },
  { value: 'DIRECTOR_FOR_OPERATIONS', label: 'Director for Operations (76–85%)' },
  { value: 'COMMANDER', label: 'Commander (86–100%)' },
];

export const AUTHORITY_OPTIONS = [
  { value: 'EVALUATOR', label: 'Evaluator — creates forms, reviews assigned forms, manages unit hazards' },
  { value: 'CREATOR', label: 'Creator — creates and submits own forms' },
  { value: 'UNIT_SAFETY_OFFICER', label: 'Unit Safety Officer — oversight of assigned units' },
  { value: 'ADMINISTRATOR', label: 'Administrator — everything' },
];
