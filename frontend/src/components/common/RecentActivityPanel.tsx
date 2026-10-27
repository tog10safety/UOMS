import type { RecentActivity } from '@/types';

function timeAgo(iso: string) {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function RecentActivityPanel({ activities }: { activities: RecentActivity[] }) {
  return (
    <div className="ops-card p-4">
      <p className="ops-label mb-3">Recent Activity</p>
      {activities.length === 0 && <p className="text-sm text-ops-textDim">No recent activity recorded.</p>}
      <ul className="space-y-3">
        {activities.map((item) => (
          <li key={item.id} className="flex items-start gap-3 border-l-2 border-ops-border pl-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ops-text">
                <span className="font-semibold text-ops-accent">{item.user}</span>{' '}
                {item.description || `${item.action.toLowerCase()} ${item.model_name}`}
              </p>
              <p className="text-xs text-ops-textDim">{timeAgo(item.created_at)}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
