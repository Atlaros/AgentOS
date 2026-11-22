import { NextRequest, NextResponse } from "next/server";
import { isValidOwnerSession, OWNER_SESSION_COOKIE } from "@/lib/auth";

const OPEN_PATHS = new Set([
  "/login",
  "/owner",
  "/signup",
  "/api/session",
  "/api/owner/session",
  "/api/owner/whatsapp",
  "/api/owner/messages",
  "/api/owner/autonomy",
  "/api/public/signup",
]);

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (OPEN_PATHS.has(pathname)) return NextResponse.next();

  const session = request.cookies.get(OWNER_SESSION_COOKIE)?.value;
  if (await isValidOwnerSession(session)) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "owner_auth_required" }, { status: 401 });
  }

  const loginUrl = new URL("/login", request.url);
  if (pathname !== "/") loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
