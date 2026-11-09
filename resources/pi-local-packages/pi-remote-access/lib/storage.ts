import { lstatSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";

/** Never include file contents or filesystem errors in UI/log output. */
export function readObject(path: string): Record<string, unknown> | null {
  try {
    if (!lstatSync(path).isFile()) return null;
    const value: unknown = JSON.parse(readFileSync(path, "utf8"));
    return value !== null && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, unknown> : null;
  } catch { return null; }
}

export function missing(path: string): boolean {
  try { lstatSync(path); return false; }
  catch (error) { return (error as NodeJS.ErrnoException).code === "ENOENT"; }
}

/** Temp files share the target directory, including for every secret write. */
export function atomicWrite(path: string, content: string): void {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  if (!lstatSync(dir).isDirectory() || lstatSync(dir).isSymbolicLink()) throw new Error("Unsafe directory");
  const temporary = join(dir, `.remote-${randomUUID()}.tmp`);
  try {
    writeFileSync(temporary, content, { encoding: "utf8", mode: 0o600, flag: "wx" });
    renameSync(temporary, path);
  } finally {
    try { unlinkSync(temporary); } catch { /* renamed or creation failed */ }
  }
}
