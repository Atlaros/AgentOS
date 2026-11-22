"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { formatCashWhen, mapCashError, readCashDetail } from "./cash-form";
import styles from "./cash.module.css";

export type CashSession = {
  id: string;
  status: string;
  opening_float: string;
  in?: string;
  out?: string;
  expected_cash: string;
  qr_in?: string;
  opened_at?: string | null;
  opened_by_name?: string | null;
  counted_cash?: string;
  difference?: string;
  close_note?: string;
  closed_at?: string | null;
  closed_by_name?: string | null;
};

type SessionPanelProps = {
  session: CashSession | null;
  hasHistory: boolean;
};

export function SessionPanel({ session, hasHistory }: SessionPanelProps) {
  const router = useRouter();
  const open = session?.status === "open";
  const [openingFloat, setOpeningFloat] = useState("0");
  const [countedCash, setCountedCash] = useState(session?.expected_cash || "");
  const [note, setNote] = useState("");
  const [showClose, setShowClose] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const difference = useMemo(() => {
    if (!open || !session) return null;
    const expected = Number(String(session.expected_cash).replace(",", "."));
    const counted = Number(String(countedCash).replace(",", "."));
    if (!Number.isFinite(expected) || !Number.isFinite(counted)) return null;
    return (counted - expected).toFixed(2);
  }, [countedCash, open, session]);

  const differenceNonzero = difference !== null && Number(difference) !== 0;

  async function openSession(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/cash/session/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opening_float: openingFloat.trim() || "0" }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo abrir la caja."));
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudo abrir la caja.");
    } finally {
      setBusy(false);
    }
  }

  async function reopenSession() {
    const pin = window.prompt("PIN de supervisor/dueño (si está configurado)") ?? "";
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/cash/session/reopen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: pin.trim() || null }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo reabrir la caja."));
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudo reabrir la caja.");
    } finally {
      setBusy(false);
    }
  }

  async function closeSession(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (differenceNonzero && !note.trim()) {
      setError(mapCashError("note_required", "La nota es obligatoria si el contado no cuadra."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/cash/session/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          counted_cash: countedCash.trim(),
          note: note.trim(),
        }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo cerrar la caja."));
        return;
      }
      setShowClose(false);
      setNote("");
      router.refresh();
    } catch {
      setError("No se pudo cerrar la caja.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className={styles.sessionBar}>
        <p className={styles.sessionMeta}>
          {open && session ? (
            <>
              <span className={`${styles.sessionStatus} ${styles.sessionStatusOpen}`}>Abierta</span>
              <span className="meta">
                {session.opened_by_name || "—"} · {formatCashWhen(session.opened_at)}
              </span>
            </>
          ) : (
            <span className={`${styles.sessionStatus} ${styles.sessionStatusClosed}`}>Cerrada</span>
          )}
        </p>
        <div className={styles.sessionActions}>
          {open ? (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => {
                setShowClose((current) => {
                  const next = !current;
                  if (next && session) {
                    setCountedCash(session.expected_cash);
                    setNote("");
                    setError("");
                  }
                  return next;
                });
              }}
            >
              {showClose ? "Cancelar cierre" : "Cerrar caja"}
            </button>
          ) : (
            <>
              <form onSubmit={openSession} className={styles.sessionActions}>
                <label>
                  Saldo inicial
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={openingFloat}
                    onChange={(event) => setOpeningFloat(event.target.value)}
                    required
                  />
                </label>
                <button type="submit" disabled={busy}>
                  {busy ? "…" : "Abrir caja"}
                </button>
              </form>
              {hasHistory ? (
                <button type="button" className="secondary" disabled={busy} onClick={reopenSession}>
                  Reabrir
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {open && showClose && session ? (
        <section className={styles.panel} aria-labelledby="cash-close-title">
          <h2 id="cash-close-title" className={styles.panelTitle}>
            Cerrar turno
          </h2>
          <p className={styles.panelLead}>
            Esperado: <strong className={styles.num}>{session.expected_cash} BOB</strong>. Si el
            contado no cuadra, la nota es obligatoria.
            {session.qr_in && Number(String(session.qr_in).replace(",", ".")) > 0 ? (
              <>
                {" "}
                QR cobrado (informativo):{" "}
                <strong className={styles.num}>{session.qr_in} BOB</strong> — no entra al
                efectivo.
              </>
            ) : null}
          </p>
          <form className={styles.closeForm} onSubmit={closeSession}>
            <label>
              Efectivo contado
              <input
                type="number"
                step="0.01"
                min="0"
                value={countedCash}
                onChange={(event) => setCountedCash(event.target.value)}
                required
              />
            </label>
            <label className={styles.wide}>
              Nota{differenceNonzero ? " (obligatoria)" : ""}
              <input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder={differenceNonzero ? "Explicá la diferencia" : "Opcional"}
                required={differenceNonzero}
              />
            </label>
            {difference !== null ? (
              <p className={differenceNonzero ? styles.warn : "meta"}>
                Diferencia: <span className={styles.num}>{difference} BOB</span>
                {differenceNonzero ? " — no cuadra" : ""}
              </p>
            ) : null}
            <button type="submit" disabled={busy}>
              {busy ? "…" : "Confirmar cierre"}
            </button>
          </form>
        </section>
      ) : null}
    </>
  );
}
