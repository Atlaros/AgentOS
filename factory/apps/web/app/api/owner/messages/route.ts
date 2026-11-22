import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

const OWNER_BUSINESS_COOKIE = "factory_owner_session";

export async function GET(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/messages`, {
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = (await upstream.json()) as unknown;
    return NextResponse.json(payload, { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}
