import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";

const OWNER_BUSINESS_COOKIE = "factory_owner_session";

function ownerAuthHeaders(token: string): HeadersInit {
  return {
    "content-type": "application/json",
    authorization: `Bearer ${token}`,
  };
}

export async function GET(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/employees`, {
      method: "GET",
      headers: { authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const payload = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: (payload as { detail?: string }).detail || "employees_failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export async function PATCH(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/employees`, {
      method: "PATCH",
      headers: ownerAuthHeaders(token),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: (payload as { detail?: string }).detail || "employees_failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export async function POST(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/employees`, {
      method: "POST",
      headers: ownerAuthHeaders(token),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: (payload as { detail?: string }).detail || "employees_failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export async function DELETE(request: NextRequest) {
  const apiBase = apiBaseUrl();
  const token = request.cookies.get(OWNER_BUSINESS_COOKIE)?.value || "";
  if (!apiBase || !token) {
    return NextResponse.json({ error: "owner_token_required" }, { status: 401 });
  }
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  try {
    const upstream = await fetch(`${apiBase}/api/owner/employees`, {
      method: "DELETE",
      headers: ownerAuthHeaders(token),
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(
        { error: (payload as { detail?: string }).detail || "employees_failed" },
        { status: upstream.status },
      );
    }
    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}
