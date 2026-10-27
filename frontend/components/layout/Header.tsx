import { useEffect, useState } from 'react';

import AccountModal from '@/components/common/AccountModal';
import { useAuth } from '@/contexts/AuthContext';

export default function Header({ title }: { title: string }) {
  const { user, logout } = useAuth();
  const [now, setNow] = useState(new Date());
  const [showAccount, setShowAccount] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-ops-border bg-ops-panel px-6">
      <div>
        <h1 className="text-lg font-semibold text-ops-text">{title}</h1>
      </div>

      <div className="flex items-center gap-6">
        <span className="font-mono text-xs text-ops-textDim">
          {now.toISOString().slice(0, 19).replace('T', ' ')} UTC
        </span>

        <div className="flex items-center gap-3 border-l border-ops-border pl-6">
          <button
            onClick={() => setShowAccount(true)}
            title="My account"
            className="flex items-center gap-3 rounded-md px-1 py-0.5 transition-colors hover:bg-ops-panelLight"
          >
            <div className="text-right">
              <p className="text-sm font-medium text-ops-text">{user?.full_name}</p>
              <p className="text-[10px] uppercase tracking-wider text-ops-accent">{user?.role}</p>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-ops-panelLight font-mono text-sm font-bold text-ops-accent">
              {user?.username.slice(0, 2).toUpperCase()}
            </div>
          </button>
          <button
            onClick={() => logout()}
            className="rounded-md border border-ops-border px-3 py-1.5 text-xs text-ops-textDim transition-colors hover:border-ops-danger hover:text-ops-danger"
          >
            Sign out
          </button>
        </div>
      </div>
      {showAccount && <AccountModal onClose={() => setShowAccount(false)} />}
    </header>
  );
}
