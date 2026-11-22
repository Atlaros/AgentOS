import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";
import {
  constantTimeEqual,
  createPanelSessionValue,
  OWNER_SESSION_COOKIE,
} from "@/lib/auth";

interface LoginBody {
  username?: unknown;
  token?: unknown;
}

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
  const ownerToken = process.env.OWNER_DASHBOARD_TOKEN || "";
  const ownerUsername = process.env.OWNER_DASHBOARD_USERNAME || "";
  if (!ownerToken || !ownerUsername) {
    return NextResponse.json({ error: "owner_auth_not_configured" }, { status: 503 });
  }

  let body: LoginBody;
  try {
    body = (await request.json()) as LoginBody;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
  const presented = typeof body.token === "string" ? body.token : "";
  let actor = "";
  if (
    constantTimeEqual(username, ownerUsername.trim().toLowerCase()) &&
    constantTimeEqual(presented, ownerToken)
  ) {
    actor = "bootstrap";
  } else if (presented) {
    const apiBase = apiBaseUrl();
    if (apiBase) {
      try {
        const upstream = await fetch(`${apiBase}/api/panel/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: username, secret: presented }),
          cache: "no-store",
        });
        if (upstream.ok) {
          const payload = (await upstream.json()) as { actor_id?: string };
          if (payload.actor_id) actor = payload.actor_id;
        }
      } catch {
        actor = "";
      }
    }
  }
  if (!actor) {
    return NextResponse.json({ error: "invalid_credentials" }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(OWNER_SESSION_COOKIE, await createPanelSessionValue(ownerToken, actor), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 8 * 60 * 60,
  });
  return response;
}

export async function DELETE(request: NextRequest) {
  if (!requestHasTrustedOrigin(request)) {
    return NextResponse.json({ error: "origin_not_allowed" }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(OWNER_SESSION_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
