import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

const OWNER_BUSINESS_COOKIE = "factory_owner_session";

function requestHasTrustedOrigin(request: NextRequest): boolean {
  const originHeader = request.headers.get("origin");
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0].trim();
  const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0].trim();
  const requestHost = forwardedHost || request.headers.get("host");
  if (!originHeader || !requestHost) return false;

  try {
    const origin = new URL(originHeader);
    const requestProtocol = forwardedProtocol
      ? `${forwardedProtocol.replace(/:$/, "")}:`
      : request.nextUrl.protocol;
    return (
      origin.host === requestHost &&
      origin.protocol === requestProtocol &&
      origin.username === "" &&
      origin.password === ""
    );
  } catch {
    return false;
  }
}

export async function POST(request: NextRequest) {
  if (!requestHasTrustedOrigin(request)) {
    return NextResponse.json({ error: "origin_not_allowed" }, { status: 403 });
  }
  const apiBase = apiBaseUrl();
  if (!apiBase) {
    return NextResponse.json({ error: "owner_api_not_configured" }, { status: 503 });
  }
  let body: { email?: unknown; secret?: unknown };
  try {
    body = (await request.json()) as { email?: unknown; secret?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const secret = typeof body.secret === "string" ? body.secret : "";
  if (!email || !secret) {
    return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, secret }),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
    }
    const payload = (await upstream.json()) as { session?: string };
    if (!payload.session) {
      return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
    }
    const response = NextResponse.json({ ok: true });
    response.cookies.set(OWNER_BUSINESS_COOKIE, payload.session, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: 8 * 60 * 60,
    });
    return response;
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export async function GET(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/business`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = (await upstream.json()) as unknown;
    return NextResponse.json(payload, { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export async function DELETE(request: NextRequest) {
  if (!requestHasTrustedOrigin(request)) {
    return NextResponse.json({ error: "origin_not_allowed" }, { status: 403 });
  }
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (apiBase && token) {
    try {
      await fetch(`${apiBase}/api/owner/session`, {
        method: "DELETE",
        headers: { authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // Cookie still clears below even if upstream is down.
    }
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(OWNER_BUSINESS_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
