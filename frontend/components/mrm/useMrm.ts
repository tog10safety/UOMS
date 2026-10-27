import { useEffect, useState } from 'react';

import { mrmApi } from '@/api/mrmApi';
import type { MrmConfig, MrmMe } from '@/types/mrm';

let configCache: MrmConfig | null = null;

/** MRM option lists (activity codes, environment choices, matrix) — fetched once per session. */
export function useMrmConfig() {
  const [config, setConfig] = useState<MrmConfig | null>(configCache);
  useEffect(() => {
    if (configCache) return;
    mrmApi.config().then((c) => { configCache = c; setConfig(c); }).catch(() => {});
  }, []);
  return config;
}

/** What the signed-in user may do in the MRM module. */
export function useMrmMe() {
  const [me, setMe] = useState<MrmMe | null>(null);
  useEffect(() => {
    mrmApi.me().then(setMe).catch(() => {});
  }, []);
  return me;
}
