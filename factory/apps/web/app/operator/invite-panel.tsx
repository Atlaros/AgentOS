"use client";

import { useState } from "react";

export function InvitePanel() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function issueInvite() {
    setBusy(true);
    setError("");
    setCode("");
    try {
      const response = await fetch("/api/backend/api/operator/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
      });
      const body = (await response.json()) as { code?: string; detail?: string; error?: string };
      if (!response.ok || !body.code) {
        throw new Error(body.detail || body.error || "No se pudo emitir la invitación.");
      }
      setCode(body.code);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo emitir la invitación.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="operator-invite-title">
      <h2 id="operator-invite-title" className="sr-only">
        Invitación de alta
      </h2>
      <p>
        <button type="button" disabled={busy} onClick={issueInvite}>
          {busy ? "Generando…" : "Emitir invitación"}
        </button>
      </p>
      {code ? (
        <p>
          Código (se muestra una vez): <code>{code}</code>
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
