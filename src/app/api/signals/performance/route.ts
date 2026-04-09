import { NextResponse } from "next/server";
import { getPerformance } from "@/server/repositories/trading-data";

export async function GET() {
  const stats = await getPerformance();
  return NextResponse.json({ stats });
}
