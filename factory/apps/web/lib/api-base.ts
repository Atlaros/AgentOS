/** Backend base URL. Accepts a full URL or a bare `host:port` (Render private network). */
export function apiBaseUrl(): string {
  const raw = (process.env.API_INTERNAL_URL || "").trim().replace(/\/$/, "");
  if (!raw) return "";
  return /^https?:\/\//.test(raw) ? raw : `http://${raw}`;
}
