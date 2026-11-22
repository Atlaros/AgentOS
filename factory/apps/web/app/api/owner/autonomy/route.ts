import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

const OWNER_BUSINESS_COOKIE = "factory_owner_session";

export async function POST(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  let body: { action?: unknown; level?: unknown };
  try {
    body = (await request.json()) as { action?: unknown; level?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const action = typeof body.action === "string" ? body.action.trim() : "";
  const level = typeof body.level === "string" ? body.level.trim() : "";
  if (!action || !level) {
    return NextResponse.json({ error: "invalid_autonomy" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/autonomy`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ action, level }),
      cache: "no-store",
    });
    const payload = (await upstream.json()) as { detail?: string };
    if (!upstream.ok) {
      return NextResponse.json(
        { error: payload.detail || "autonomy_failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}
