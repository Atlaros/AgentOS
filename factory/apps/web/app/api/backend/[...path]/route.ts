import { NextRequest, NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api-base";
import { readPanelActor, OWNER_SESSION_COOKIE } from "@/lib/auth";

interface BackendRouteContext {
  params: Promise<{ path: string[] }>;
}

async function forward(request: NextRequest, context: BackendRouteContext) {
  const actor = await readPanelActor(request.cookies.get(OWNER_SESSION_COOKIE)?.value);
  if (!actor) {
    return NextResponse.json({ error: "owner_auth_required" }, { status: 401 });
  }

  const token = process.env.OWNER_DASHBOARD_TOKEN || "";
  const apiBase = apiBaseUrl();
  if (!token || !apiBase) {
    return NextResponse.json({ error: "owner_api_not_configured" }, { status: 503 });
  }

  const { path } = await context.params;
  const target = new URL(
    `${path.map((part) => encodeURIComponent(part)).join("/")}${request.nextUrl.search}`,
    `${apiBase.replace(/\/$/, "")}/`,
  );
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("authorization", `Bearer ${token}`);
  headers.set("x-panel-actor", actor);

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
    const responseHeaders = new Headers();
    const responseType = upstream.headers.get("content-type");
    if (responseType) responseHeaders.set("content-type", responseType);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) responseHeaders.set("content-disposition", disposition);
    responseHeaders.set("cache-control", "no-store");
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ error: "owner_api_unavailable" }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
