import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl, config } from "@/lib/config";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const res = await fetch(getBackendUrl(config.api.signals.generate), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(45_000),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : 500 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unknown error";
    return NextResponse.json(
      { status: "error", message: `Backend unreachable: ${msg}` },
      { status: 502 }
    );
  }
}
