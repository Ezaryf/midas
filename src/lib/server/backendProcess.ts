import { spawn } from "node:child_process";
import { existsSync, mkdirSync, openSync } from "node:fs";
import path from "node:path";

import { config } from "@/lib/config";

type BackendStarterState = {
  starting: boolean;
  lastStartAt: number;
};

const globalState = globalThis as typeof globalThis & {
  __midasBackendStarter?: BackendStarterState;
};

function isLocalBackend(): boolean {
  try {
    const url = new URL(config.backend.http);
    return ["127.0.0.1", "localhost"].includes(url.hostname);
  } catch {
    return false;
  }
}

export function maybeStartLocalBackend(): boolean {
  if (process.env.NODE_ENV === "production" || !isLocalBackend()) {
    return false;
  }

  const state =
    globalState.__midasBackendStarter ??
    (globalState.__midasBackendStarter = { starting: false, lastStartAt: 0 });

  const now = Date.now();
  if (state.starting && now - state.lastStartAt < 20_000) {
    return true;
  }

  const backendDir = path.join(process.cwd(), "backend");
  const runner = path.join(backendDir, "run_midas.py");
  if (!existsSync(runner)) {
    return false;
  }

  const logDir = path.join(backendDir, "logs");
  mkdirSync(logDir, { recursive: true });

  const out = openSync(path.join(logDir, "next-backend.out.log"), "a");
  const err = openSync(path.join(logDir, "next-backend.err.log"), "a");
  const child = spawn("python", ["-u", "run_midas.py", "--auto-trade"], {
    cwd: backendDir,
    detached: true,
    stdio: ["ignore", out, err],
    windowsHide: false,
  });

  child.unref();
  state.starting = true;
  state.lastStartAt = now;
  return true;
}
