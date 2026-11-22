export const OWNER_SESSION_COOKIE = "closet_owner_session";

const SESSION_CONTEXT = "agent-ia-panel-actor-v2";

export async function createPanelSessionValue(secret: string, actor: string): Promise<string> {
  const signature = await signActor(secret, actor);
  return `${actor}.${signature}`;
}

export function constantTimeEqual(left: string, right: string): boolean {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

export async function readPanelActor(value: string | undefined): Promise<string | null> {
  const secret = process.env.OWNER_DASHBOARD_TOKEN || "";
  if (!secret || !value) return null;
  const splitAt = value.lastIndexOf(".");
  if (splitAt <= 0) return null;
  const actor = value.slice(0, splitAt);
  const signature = value.slice(splitAt + 1);
  if (!isActor(actor)) return null;
  const expected = await signActor(secret, actor);
  if (!constantTimeEqual(signature, expected)) return null;
  return actor;
}

export async function isValidOwnerSession(value: string | undefined): Promise<boolean> {
  return (await readPanelActor(value)) !== null;
}

function isActor(actor: string): boolean {
  return actor === "bootstrap" || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(actor);
}

async function signActor(secret: string, actor: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`${SESSION_CONTEXT}:${actor}`),
  );
  return Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
