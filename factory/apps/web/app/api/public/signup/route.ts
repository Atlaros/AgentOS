import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

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
    return NextResponse.json({ error: "signup_api_not_configured" }, { status: 503 });
  }
  let body: { name?: unknown; industry?: unknown; invite?: unknown };
  try {
    body = (await request.json()) as { name?: unknown; industry?: unknown; invite?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const industry = typeof body.industry === "string" ? body.industry.trim().toLowerCase() : "";
  const invite = typeof body.invite === "string" ? body.invite.trim() : "";
  if (!name || !industry) {
    return NextResponse.json({ error: "invalid_signup" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/public/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(request.headers.get("x-forwarded-for")
          ? { "X-Forwarded-For": request.headers.get("x-forwarded-for") as string }
          : {}),
      },
      body: JSON.stringify({ name, industry, invite }),
      cache: "no-store",
    });
    const payload = (await upstream.json()) as Record<string, unknown>;
    if (!upstream.ok) {
      const detail = typeof payload.detail === "string" ? payload.detail : "signup_failed";
      return NextResponse.json({ error: detail }, { status: upstream.status });
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "signup_api_unavailable" }, { status: 502 });
  }
}
