import type { RiskAlertSummary } from '@/types';

const SEVERITY_STYLES: Record<RiskAlertSummary['severity'], string> = {
  LOW: 'bg-ops-success/10 text-ops-success border-ops-success/30',
  MEDIUM: 'bg-ops-warning/10 text-ops-warning border-ops-warning/30',
  HIGH: 'bg-ops-danger/10 text-ops-danger border-ops-danger/30',
  CRITICAL: 'bg-ops-danger/20 text-ops-danger border-ops-danger/50 animate-pulse',
};

export default function RiskAlertsPanel({ alerts }: { alerts: RiskAlertSummary[] }) {
  return (
    <div className="ops-card p-4">
      <p className="ops-label mb-3">Risk Alerts</p>
      {alerts.length === 0 && <p className="text-sm text-ops-textDim">No open risk alerts.</p>}
      <div className="space-y-2">
        {alerts.map((alert) => (
          <div key={alert.id} className={`rounded-md border px-3 py-2 ${SEVERITY_STYLES[alert.severity]}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">{alert.title}</span>
              <span className="font-mono text-[10px] uppercase tracking-wider">{alert.severity}</span>
            </div>
            {alert.mission && <p className="mt-0.5 text-xs opacity-80">Mission: {alert.mission}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
