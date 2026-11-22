"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { DigestControls } from "./digest-controls";
import styles from "./metrics.module.css";

export type ThresholdValues = {
  qr_pending_hours: number;
  inactive_days: number;
  digest_whatsapp_enabled: boolean;
  stock_note: string;
  can_edit: boolean;
  digest_destinations?: string[];
};

type ThresholdsFormProps = {
  initial: ThresholdValues;
};

export function ThresholdsForm({ initial }: ThresholdsFormProps) {
  const router = useRouter();
  const [hours, setHours] = useState(String(initial.qr_pending_hours));
  const [days, setDays] = useState(String(initial.inactive_days));
  const [digest, setDigest] = useState(initial.digest_whatsapp_enabled);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const destinations = initial.digest_destinations ?? [];

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const hoursN = Number(hours);
    const daysN = Number(days);
    if (!Number.isInteger(hoursN) || hoursN < 1 || !Number.isInteger(daysN) || daysN < 1) {
      setSaved("");
      setError("Los umbrales tienen que ser números enteros mayores que cero.");
      return;
    }
    setBusy(true);
    setError("");
    setSaved("");
    try {
      const res = await fetch("/api/backend/api/analytics/thresholds", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          qr_pending_hours: hoursN,
          inactive_days: daysN,
          digest_whatsapp_enabled: digest,
        }),
      });
      if (!res.ok) {
        setError("No se pudieron guardar los umbrales.");
        return;
      }
      setSaved("Umbrales guardados.");
      router.refresh();
    } catch {
      setError("No se pudieron guardar los umbrales.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.thresholds} onSubmit={onSubmit}>
      <section className={styles.drawerSection}>
        <h3>Umbrales</h3>
        <div className={styles.fields}>
          <label>
            QR pendiente (horas)
            <input
              name="qr_pending_hours"
              inputMode="numeric"
              value={hours}
              onChange={(event) => setHours(event.target.value)}
            />
          </label>
          <label>
            Cliente inactivo (días)
            <input
              name="inactive_days"
              inputMode="numeric"
              value={days}
              onChange={(event) => setDays(event.target.value)}
            />
          </label>
        </div>
        <p className={styles.note}>{initial.stock_note}</p>
      </section>
      <section className={styles.drawerSection}>
        <h3>Resumen diario</h3>
        <label className={styles.switch}>
          <span>Resumen diario por WhatsApp al dueño</span>
          <input
            type="checkbox"
            role="switch"
            name="digest_whatsapp_enabled"
            checked={digest}
            aria-checked={digest}
            onChange={(event) => setDigest(event.target.checked)}
          />
        </label>
        <p className={styles.note}>
          Si está activo, sale como máximo un mensaje por día (La Paz) y solo cuando hay alertas.
        </p>
        {destinations.length > 0 ? (
          <p className={styles.note}>Destino: {destinations.join(", ")}</p>
        ) : null}
        <DigestControls />
      </section>
      <button type="submit" disabled={busy}>
        Guardar
      </button>
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
    </form>
  );
}
