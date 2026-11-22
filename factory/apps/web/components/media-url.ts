/** Proxy panel media paths through the Next backend rewrite. */

export function proxyMediaUrl(url?: string | null): string | undefined {
  const raw = (url || "").trim();
  if (!raw) return undefined;
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
  if (raw.startsWith("/api/backend/")) return raw;
  if (raw.startsWith("/")) return `/api/backend${raw}`;
  return undefined;
}

export function isHttpUrl(url?: string | null): boolean {
  const raw = (url || "").trim();
  return raw.startsWith("http://") || raw.startsWith("https://");
}
