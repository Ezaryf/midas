import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/config";

const MT5_VALIDATE_PATH = "/api/mt5/validate";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const res = await fetch(getBackendUrl(MT5_VALIDATE_PATH), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(20_000),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { status: "error", message: "Backend unreachable — start the server first." },
      { status: 502 }
    );
  }
}
