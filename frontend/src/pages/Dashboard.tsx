import { useEffect, useState } from 'react';

import { dashboardApi } from '@/api/endpoints';
import OperationalMap from '@/components/common/OperationalMap';
import RecentActivityPanel from '@/components/common/RecentActivityPanel';
import RiskAlertsPanel from '@/components/common/RiskAlertsPanel';
import StatCard from '@/components/common/StatCard';
import StatusBreakdown from '@/components/common/StatusBreakdown';
import type { DashboardSummary } from '@/types';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      try {
        const data = await dashboardApi.getSummary();
        if (isMounted) setSummary(data);
      } catch {
        if (isMounted) setError('Unable to load dashboard data.');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  if (isLoading) {
    return <p className="text-sm text-ops-textDim">Loading operational picture…</p>;
  }

  if (error || !summary) {
    return <p className="text-sm text-ops-danger">{error || 'No data available.'}</p>;
  }

  const { operational_status } = summary;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Personnel" value={operational_status.total_personnel} />
        <StatCard label="Vehicles" value={operational_status.total_vehicles} />
        <StatCard label="Aircraft" value={operational_status.total_aircraft} />
        <StatCard label="Active Missions" value={operational_status.active_missions} accent="success" />
        <StatCard
          label="Open Risk Alerts"
          value={operational_status.open_risk_alerts}
          accent={operational_status.open_risk_alerts > 0 ? 'danger' : 'success'}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <OperationalMap points={summary.map_overview} />
        </div>
        <RiskAlertsPanel alerts={summary.risk_alerts} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatusBreakdown
          title="Personnel Summary"
          data={summary.personnel_summary.by_status}
          total={summary.personnel_summary.total}
        />
        <StatusBreakdown
          title="Vehicle Status"
          data={summary.vehicle_status.by_status}
          total={summary.vehicle_status.total}
        />
        <StatusBreakdown
          title="Aircraft Flying Status"
          data={summary.aircraft_flying_status.by_status}
          total={summary.aircraft_flying_status.total}
        />
        <StatusBreakdown
          title="Mission Status"
          data={summary.mission_status.by_status}
          total={summary.mission_status.total}
        />
      </div>

      <RecentActivityPanel activities={summary.recent_activities} />
    </div>
  );
}
