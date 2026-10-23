import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { AppConfig } from "@/api/types";

/**
 * The upload size limit and session lifetime are configured on the server
 * (MAX_UPLOAD_MB, SESSION_TTL_MINUTES), so public pages read them from
 * /api/config instead of hard-coding numbers that could be wrong.
 */
let pending: Promise<AppConfig | null> | null = null;

export function loadLimits(): Promise<AppConfig | null> {
  pending ??= api.config().catch(() => {
    pending = null; // try again next time
    return null;
  });
  return pending;
}

export function useServerLimits(): AppConfig | null {
  const [config, setConfig] = useState<AppConfig | null>(null);
  useEffect(() => {
    let alive = true;
    void loadLimits().then((c) => alive && setConfig(c));
    return () => {
      alive = false;
    };
  }, []);
  return config;
}

/** Replace {limit} and {ttl} in content text; neutral wording while the values are unknown. */
export function fillLimits(text: string, config: Pick<AppConfig, "max_upload_mb" | "session_ttl_minutes"> | null): string {
  return text
    .replace(/\{limit\}/g, config ? `${config.max_upload_mb} MB` : "the server's size limit")
    .replace(/\{ttl\}/g, config && config.session_ttl_minutes > 0 ? `${config.session_ttl_minutes} minutes` : "a period");
}

/** One sentence on how long the dataset is kept, for the workspace. */
export function keepText(config: Pick<AppConfig, "session_ttl_minutes" | "save_sessions"> | null): string {
  const ttl = config?.session_ttl_minutes ?? 30;
  if (config?.save_sessions)
    return ttl > 0
      ? `Saved on this computer; deleted after ${ttl} min of inactivity.`
      : "Saved on this computer until you delete it, also after a restart.";
  return ttl > 0 ? `Deleted after ${ttl} min of inactivity.` : "Kept until you delete it or the server restarts.";
}
