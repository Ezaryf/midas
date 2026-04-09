import { type NextRequest, NextResponse } from "next/server";

export async function proxy(request: NextRequest) {
  // No authentication — local internal tool.
  // Just let every request through.
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
