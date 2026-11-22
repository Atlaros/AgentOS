import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

const OWNER_BUSINESS_COOKIE = "factory_owner_session";

export async function POST(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  let body: { phone_number_id?: unknown; access_token?: unknown };
  try {
    body = (await request.json()) as { phone_number_id?: unknown; access_token?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const phone = typeof body.phone_number_id === "string" ? body.phone_number_id.trim() : "";
  const accessToken = typeof body.access_token === "string" ? body.access_token.trim() : "";
  try {
    const upstream = await fetch(`${apiBase}/api/owner/whatsapp`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        phone_number_id: phone,
        ...(accessToken ? { access_token: accessToken } : {}),
      }),
      cache: "no-store",
    });
    const payload = (await upstream.json()) as { detail?: string };
    if (!upstream.ok) {
      return NextResponse.json(
        { error: payload.detail || "phone_invalid" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}
