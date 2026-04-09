import { NextResponse } from "next/server";
import { clearSignals, listSignals } from "@/server/repositories/trading-data";

export async function GET() {
  const signals = await listSignals();
  return NextResponse.json({ signals });
}

export async function DELETE() {
  await clearSignals();
  return NextResponse.json({ ok: true });
}
