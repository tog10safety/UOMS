import React, { createContext, useContext, useEffect, useState } from 'react';

import { authApi } from '@/api/endpoints';
import { tokenStorage } from '@/api/client';
import type { PermissionAction, PermissionModule, User } from '@/types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-reads /auth/me/ (e.g. after a profile edit or password change). */
  refreshUser: () => Promise<void>;
  hasRole: (...roles: User['role'][]) => boolean;
  /**
   * Mirrors the backend's HasModulePermission check, driven by the same
   * `permissions` map the API returns on /auth/me/ — so a button only
   * shows when the underlying API call would actually succeed. This is
   * a UX convenience only: the API enforces this independently and must
   * never be bypassed just because a button was hidden.
   */
  can: (module: PermissionModule, action: PermissionAction) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const bootstrap = async () => {
      const token = tokenStorage.getAccess();
      if (!token) {
        setIsLoading(false);
        return;
      }
      try {
        const me = await authApi.me();
        setUser(me);
      } catch {
        tokenStorage.clear();
      } finally {
        setIsLoading(false);
      }
    };
    bootstrap();
  }, []);

  const login = async (username: string, password: string) => {
    const data = await authApi.login(username, password);
    tokenStorage.set(data.access, data.refresh);
    setUser(data.user);
  };

  const logout = async () => {
    const refresh = tokenStorage.getRefresh();
    try {
      if (refresh) await authApi.logout(refresh);
    } catch {
      // Best-effort; clear local state regardless.
    }
    tokenStorage.clear();
    setUser(null);
  };

  const refreshUser = async () => {
    setUser(await authApi.me());
  };

  const hasRole = (...roles: User['role'][]) => !!user && roles.includes(user.role);

  const can = (module: PermissionModule, action: PermissionAction) => {
    if (!user) return false;
    if (user.role === 'ADMIN') return true;
    return !!user.permissions[module]?.includes(action);
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, login, logout, refreshUser, hasRole, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
