import { FormEvent, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '@/contexts/AuthContext';

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (isAuthenticated) {
    const redirectTo = (location.state as { from?: Location })?.from?.pathname ?? '/';
    return <Navigate to={redirectTo} replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch {
      setError('Invalid username or password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-ops-bg bg-[radial-gradient(circle_at_top,_#16213a,_#0b1220)]">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-lg bg-ops-accent/10 font-mono text-2xl font-bold text-ops-accent">
            U
          </div>
          <h1 className="text-xl font-bold tracking-wide text-ops-text">UOMS</h1>
          <p className="text-xs text-ops-textDim">Unit Operations Management System</p>
        </div>

        <form onSubmit={handleSubmit} className="ops-card space-y-4 p-6">
          <div>
            <label className="ops-label mb-1 block">Username</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
            />
          </div>

          <div>
            <label className="ops-label mb-1 block">Password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-md border border-ops-border bg-ops-panelLight px-3 py-2 text-sm text-ops-text outline-none focus:border-ops-accent"
            />
          </div>

          {error && (
            <p className="rounded-md border border-ops-danger/30 bg-ops-danger/10 px-3 py-2 text-xs text-ops-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-md bg-ops-accent py-2 text-sm font-semibold text-ops-bg transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {isSubmitting ? 'Authenticating…' : 'Sign In'}
          </button>
        </form>

        <p className="mt-4 text-center text-[10px] text-ops-textDim">
          Authorized personnel only. All access is logged.
        </p>
      </div>
    </div>
  );
}
