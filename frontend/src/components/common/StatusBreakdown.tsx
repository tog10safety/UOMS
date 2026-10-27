interface StatusBreakdownProps {
  title: string;
  data: Record<string, number>;
  total: number;
}

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'bg-ops-success',
  AVAILABLE: 'bg-ops-success',
  ONGOING: 'bg-ops-accent',
  IN_FLIGHT: 'bg-ops-accent',
  ON_MISSION: 'bg-ops-accent',
  SCHEDULED: 'bg-ops-warning',
  PLANNED: 'bg-ops-warning',
  TRAINING: 'bg-ops-warning',
  ON_LEAVE: 'bg-ops-warning',
  DEPLOYED: 'bg-ops-accent',
  MAINTENANCE: 'bg-ops-danger',
  MEDICAL: 'bg-ops-danger',
  OUT_OF_SERVICE: 'bg-ops-danger',
  GROUNDED: 'bg-ops-textDim',
  CANCELLED: 'bg-ops-danger',
  COMPLETED: 'bg-ops-textDim',
  SEPARATED: 'bg-ops-textDim',
  APPROVED: 'bg-ops-accent',
};

function formatLabel(key: string) {
  return key
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default function StatusBreakdown({ title, data, total }: StatusBreakdownProps) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);

  return (
    <div className="ops-card p-4">
      <p className="ops-label mb-3">{title}</p>
      {entries.length === 0 && <p className="text-sm text-ops-textDim">No records yet.</p>}
      <div className="space-y-2">
        {entries.map(([status, count]) => {
          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
          return (
            <div key={status}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-ops-text">{formatLabel(status)}</span>
                <span className="font-mono text-ops-textDim">{count}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-ops-panelLight">
                <div
                  className={`h-full rounded-full ${STATUS_COLORS[status] ?? 'bg-ops-accent'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
