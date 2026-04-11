import { NextResponse } from "next/server";
import { getBackendUrl, config } from "@/lib/config";

export async function GET() {
  try {
    const res = await fetch(getBackendUrl(config.api.health), {
      signal: AbortSignal.timeout(3000),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: "offline" }, { status: 502 });
  }
}
