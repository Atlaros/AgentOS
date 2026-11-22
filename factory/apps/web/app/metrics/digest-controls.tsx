"use client";

import { useState } from "react";

import styles from "./metrics.module.css";

const DIGEST_STATUS = {
  SENT: "sent",
  PREVIEW: "preview",
  NO_ALERTS: "no_alerts",
} as const;

type DigestBody = {
  status?: string;
  text_preview?: string;
};

export function DigestControls() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [preview, setPreview] = useState("");

  async function requestPreview() {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const res = await fetch("/api/backend/api/analytics/digest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true, dry_run: true }),
      });
      if (!res.ok) {
        setError("No se pudo preparar el resumen.");
        return;
      }
      const body = (await res.json()) as DigestBody;
      if (body.status === DIGEST_STATUS.NO_ALERTS) {
        setPreview("");
        setSaved("No hay alertas activas. No se envió nada.");
        return;
      }
      if (body.status === DIGEST_STATUS.PREVIEW && body.text_preview) {
        setPreview(body.text_preview);
        return;
      }
      setError("No se pudo preparar el resumen.");
    } catch {
      setError("No se pudo preparar el resumen.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmSend() {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const res = await fetch("/api/backend/api/analytics/digest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });
      if (!res.ok) {
        setError("No se pudo enviar el resumen.");
        return;
      }
      const body = (await res.json()) as DigestBody;
      setPreview("");
      if (body.status === DIGEST_STATUS.SENT) {
        setSaved("Resumen enviado al dueño.");
        return;
      }
      if (body.status === DIGEST_STATUS.NO_ALERTS) {
        setSaved("No hay alertas activas. No se envió nada.");
        return;
      }
      setSaved("No se envió el resumen.");
    } catch {
      setError("No se pudo enviar el resumen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.digest}>
      <button type="button" onClick={requestPreview} disabled={busy}>
        Enviar resumen ahora
      </button>
      <p className={styles.note}>
        El envío manual manda el resumen de hoy aunque el resumen diario esté apagado. Si no hay
        alertas, no sale ningún mensaje.
      </p>
      {preview ? (
        <div className={styles.preview}>
          <p className={styles.note}>Así se vería el mensaje. Confirmá para enviarlo.</p>
          <pre className={styles.previewText}>{preview}</pre>
          <div className={styles.previewActions}>
            <button type="button" onClick={confirmSend} disabled={busy}>
              Enviar
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setPreview("")}
              disabled={busy}
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {saved ? (
        <p className={styles.saved} role="status">
          {saved}
        </p>
      ) : null}
    </div>
  );
}
