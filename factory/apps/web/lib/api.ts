import "server-only";
import { apiBaseUrl } from "./api-base";

const API_BASE = apiBaseUrl();
const TOKEN = process.env.OWNER_DASHBOARD_TOKEN || "";

export type ConversationSummary = {
  id: string;
  wa_number: string;
  name: string | null;
  last_text: string;
  needs_human: boolean;
  human_takeover: boolean;
  message_count: number;
};

function headers(): HeadersInit {
  if (!API_BASE || !TOKEN) throw new Error("owner_api_not_configured");
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: headers(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}
