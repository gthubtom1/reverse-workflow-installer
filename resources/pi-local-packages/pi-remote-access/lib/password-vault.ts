import { createHash, randomInt } from "node:crypto";
import { lstatSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { atomicWrite, readObject } from "./storage.ts";

export const PASSWORD_REFERENCE = "<CRED:pi-web-remote/password>";
const digest = (value: string): string => createHash("sha256").update(value).digest("hex");

/** SEEP_CRED_ROOT replaces ~/.seep/secrets, not the per-service directory. */
export function credentialPaths(env: NodeJS.ProcessEnv = process.env) {
  const configured = env.SEEP_CRED_ROOT?.trim();
  const expanded = configured === "~" ? homedir()
    : configured?.startsWith("~/") || configured?.startsWith("~\\") ? join(homedir(), configured.slice(2))
    : configured;
  const root = resolve(expanded || join(homedir(), ".seep", "secrets"));
  const directory = join(root, "pi-web-remote");
  return { root, directory, password: join(directory, "password"), state: join(directory, "state.json") };
}

/** CSPRNG with unbiased character selection; no Math.random, shell or subprocess. */
export function generatePassword(length = 24): string {
  if (!Number.isSafeInteger(length) || length < 16 || length > 256) throw new RangeError("Invalid password length");
  const alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
  return Array.from({ length }, () => alphabet[randomInt(alphabet.length)]).join("");
}

export class PasswordVault {
  readonly paths: ReturnType<typeof credentialPaths>;
  constructor(env: NodeJS.ProcessEnv) { this.paths = credentialPaths(env); }

  private prepare(): void {
    mkdirSync(this.paths.root, { recursive: true, mode: 0o700 });
    if (lstatSync(this.paths.root).isSymbolicLink()) throw new Error("Unsafe credential root");
    mkdirSync(this.paths.directory, { recursive: true, mode: 0o700 });
    if (lstatSync(this.paths.directory).isSymbolicLink()) throw new Error("Unsafe credential directory");
  }

  /** A plain cred-store password without an explicit matching marker is inert. */
  readEnabled(): string | null {
    try {
      if (lstatSync(this.paths.root).isSymbolicLink() || lstatSync(this.paths.directory).isSymbolicLink()) return null;
      const state = readObject(this.paths.state);
      if (state?.version !== 1 || state.passwordState !== "enabled" || typeof state.sha256 !== "string") return null;
      const stat = lstatSync(this.paths.password);
      if (!stat.isFile() || stat.isSymbolicLink()) return null;
      const value = readFileSync(this.paths.password, "utf8");
      return value.length > 0 && digest(value) === state.sha256 ? value : null;
    } catch { return null; }
  }

  generate(): { saved: true; value: string } | { saved: false } {
    try {
      this.prepare();
      const value = generatePassword();
      // Plain value file is compatible with cred-store. All staging stays in
      // this directory. The fingerprint prevents a partial rotation from being
      // restored using the previous enabled marker after a failed state write.
      atomicWrite(this.paths.password, value);
      atomicWrite(this.paths.state, `${JSON.stringify({ version: 1, passwordState: "enabled", sha256: digest(value) }, null, 2)}\n`);
      return { saved: true, value };
    } catch { return { saved: false }; }
  }

  disable(): boolean {
    try {
      this.prepare();
      // Keep the plain value for local credential tools, but make it inert.
      // Commit this durable tombstone before clearing the runtime password.
      atomicWrite(this.paths.state, `${JSON.stringify({ version: 1, passwordState: "disabled" }, null, 2)}\n`);
      return true;
    } catch { return false; }
  }
}
