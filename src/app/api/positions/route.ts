import { NextResponse } from "next/server";
import { getBackendUrl, config } from "@/lib/config";
import { maybeStartLocalBackend } from "@/lib/server/backendProcess";

export const runtime = "nodejs";

export async function GET() {
  try {
    const response = await fetch(getBackendUrl(config.api.positions), {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: "Failed to fetch positions" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    maybeStartLocalBackend();
    console.error("Error fetching positions:", error);
    return NextResponse.json(
      { error: "Backend connection failed" },
      { status: 503 }
    );
  }
}
