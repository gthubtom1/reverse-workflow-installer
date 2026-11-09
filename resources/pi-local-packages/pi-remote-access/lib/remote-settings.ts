import { join } from "node:path";
import { atomicWrite, missing, readObject } from "./storage.ts";

export const REMOTE_SETTINGS_NAME = "pi-web-remote.json";
export interface RemoteSettings {
  lastMode: "lan" | "tailscale" | null;
  allowedHosts: string[];
}
const defaults = (): RemoteSettings => ({ lastMode: null, allowedHosts: [] });
export function remoteSettingsPath(agentDir: string): string { return join(agentDir, REMOTE_SETTINGS_NAME); }

export function normalizeRemoteSettings(input: unknown): RemoteSettings {
  if (!input || typeof input !== "object" || Array.isArray(input)) return defaults();
  const raw = input as Record<string, unknown>;
  return {
    lastMode: raw.lastMode === "lan" || raw.lastMode === "tailscale" ? raw.lastMode : null,
    allowedHosts: Array.isArray(raw.allowedHosts)
      ? [...new Set(raw.allowedHosts.filter((v): v is string => typeof v === "string").map(v => v.trim()).filter(Boolean))]
      : [],
  };
}

/** Legacy password is deliberately never returned or activated. */
export function readRemoteSettings(agentDir: string): RemoteSettings {
  return normalizeRemoteSettings(readObject(remoteSettingsPath(agentDir)));
}

export function writeRemoteSettings(patch: Partial<RemoteSettings>, agentDir: string): RemoteSettings & { saved: boolean } {
  const path = remoteSettingsPath(agentDir);
  const stored = readObject(path);
  const current = normalizeRemoteSettings(stored);
  // Do not clobber damaged data or rewrite a nonempty/unknown legacy secret.
  // Only explicit null or an empty string may be removed during an ordinary save.
  const unsafeLegacyPassword = stored && Object.hasOwn(stored, "password")
    && stored.password !== null && stored.password !== "";
  if ((!stored && !missing(path)) || unsafeLegacyPassword || Object.hasOwn(patch, "password")) {
    return { ...current, saved: false };
  }
  const next = normalizeRemoteSettings({ ...current, ...patch });
  try {
    // Only these two fields are owned here; unknown existing fields survive.
    const output: Record<string, unknown> = { ...stored, ...next };
    delete output.password;
    atomicWrite(path, `${JSON.stringify(output, null, 2)}\n`);
    return { ...next, saved: true };
  } catch { return { ...current, saved: false }; }
}

export function mergeAllowedHosts(hosts: readonly string[], host: string): string[] {
  return [...new Set([...hosts, host].map(v => v.trim()).filter(Boolean))];
}
export function allowedHostsEnv(hosts: readonly string[]): string {
  return [...new Set(hosts.map(v => v.trim()).filter(Boolean))].join(",");
}
