import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { notificationsApi } from '@/api/missionOps';
import type { AppNotification } from '@/types/missionOps';
import { formatDateTime } from '@/utils/errors';

/** Bell with an unread badge; clicking a notification marks it read and opens its link. */
export default function NotificationBell() {
  const navigate = useNavigate();
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);

  const refreshCount = useCallback(() => { notificationsApi.unreadCount().then(setCount).catch(() => {}); }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(refreshCount, 45_000);
    return () => clearInterval(timer);
  }, [refreshCount]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    notificationsApi.list({ page_size: 15 }).then((d) => setItems(d.results)).catch(() => setItems([])).finally(() => setLoading(false));
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const openItem = async (n: AppNotification) => {
    if (!n.is_read) {
      await notificationsApi.read(n.id).catch(() => {});
      setItems((list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
      refreshCount();
    }
    setOpen(false);
    if (n.link) navigate(n.link);
  };

  const markAll = async () => {
    await notificationsApi.readAll().catch(() => {});
    setItems((list) => list.map((x) => ({ ...x, is_read: true })));
    setCount(0);
  };

  return (
    <div className="relative" ref={box}>
      <button onClick={() => setOpen((o) => !o)} aria-label={`Notifications${count ? ` (${count} unread)` : ''}`} title="Notifications"
              className="relative rounded-md p-2 text-ops-textDim transition-colors hover:bg-ops-panelLight hover:text-ops-text">
        <span aria-hidden className="text-base">🔔</span>
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-[1.1rem] rounded-full bg-ops-danger px-1 text-center font-mono text-[10px] font-bold leading-4 text-white">{count > 99 ? '99+' : count}</span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-96 max-w-[90vw] overflow-hidden rounded-md border border-ops-border bg-ops-panel shadow-xl">
          <div className="flex items-center justify-between border-b border-ops-border px-4 py-2">
            <p className="ops-label">Notifications</p>
            {count > 0 && <button onClick={markAll} className="text-xs text-ops-accent hover:underline">Mark all read</button>}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {loading && <p className="p-4 text-xs text-ops-textDim">Loading…</p>}
            {!loading && items.length === 0 && <p className="p-4 text-center text-sm text-ops-textDim">You have no notifications.</p>}
            {items.map((n) => (
              <button key={n.id} onClick={() => openItem(n)} className={`block w-full border-b border-ops-border px-4 py-3 text-left last:border-0 hover:bg-ops-panelLight ${n.is_read ? '' : 'bg-ops-accent/5'}`}>
                <p className={`text-sm ${n.is_read ? 'text-ops-textDim' : 'font-medium text-ops-text'}`}>{n.title}</p>
                {n.message && <p className="line-clamp-2 text-xs text-ops-textDim">{n.message}</p>}
                <p className="mt-0.5 text-[10px] text-ops-textDim">{formatDateTime(n.created_at)}</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
