import { NextResponse } from "next/server";
import { getBackendUrl, config } from "@/lib/config";
import { maybeStartLocalBackend } from "@/lib/server/backendProcess";

export const runtime = "nodejs";

export async function GET() {
  try {
    const res = await fetch(getBackendUrl(config.api.health), {
      signal: AbortSignal.timeout(3000),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    const started = maybeStartLocalBackend();
    return NextResponse.json(
      {
        status: started ? "starting" : "offline",
        message: started
          ? "Backend was offline. Starting local Midas backend and MT5 bridge..."
          : "Backend offline",
      },
      { status: started ? 202 : 502 },
    );
  }
}
