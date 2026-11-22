"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./reports.module.css";

const NOTICE_KIND = {
  COLLECTIONS: "collections",
  FOLLOW_UP: "follow_up",
  REPURCHASE: "repurchase",
} as const;

type NoticeKind = (typeof NOTICE_KIND)[keyof typeof NOTICE_KIND];

interface ReminderPreview {
  body: string;
  customer_label: string;
  wa_number: string;
  kind: NoticeKind;
  would_send: boolean;
}

interface ReminderButtonProps {
  customerId: string;
  kind?: NoticeKind;
}

export function ReminderButton({ customerId, kind }: ReminderButtonProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [preview, setPreview] = useState<ReminderPreview | null>(null);

  if (!customerId.trim()) return null;

  async function requestPreview() {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const payload: { customer_id: string; kind?: NoticeKind } = { customer_id: customerId };
      if (kind) payload.kind = kind;
      const res = await fetch("/api/backend/api/reminders/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.status === 400) {
        setPreview(null);
        setError("No hay un aviso para esta persona.");
        return;
      }
      if (!res.ok) {
        setError("No se pudo preparar el aviso.");
        return;
      }
      const body = (await res.json()) as ReminderPreview;
      setPreview(body);
    } catch {
      setError("No se pudo preparar el aviso.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmSend() {
    if (!preview) return;
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const res = await fetch("/api/backend/api/reminders/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          kind: preview.kind,
          confirm: true,
        }),
      });
      if (!res.ok) {
        setError("No se pudo enviar el aviso.");
        return;
      }
      setPreview(null);
      setSaved("Aviso enviado. No confirma el pago.");
      router.refresh();
    } catch {
      setError("No se pudo enviar el aviso.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.reminder}>
      <button type="button" className={styles.actionButton} onClick={requestPreview} disabled={busy}>
        Recordar
      </button>
      {preview ? (
        <div className={styles.confirmBox} role="region" aria-label="Confirmar aviso">
          <p className={styles.confirmMeta}>
            {preview.customer_label} · {preview.wa_number}
          </p>
          <p className={styles.confirmText}>{preview.body}</p>
          <div className={styles.confirmActions}>
            <button type="button" onClick={confirmSend} disabled={busy}>
              Confirmar
            </button>
            <button type="button" onClick={() => setPreview(null)} disabled={busy}>
              Cancelar
            </button>
          </div>
        </div>
      ) : null}
      {saved ? (
        <p className={styles.saved} role="status">
          {saved}
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
