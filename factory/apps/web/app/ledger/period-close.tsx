"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./ledger.module.css";

export type AccountingPeriodRow = {
  id: string;
  from: string;
  to: string;
  status: string;
  closed_at?: string | null;
  closed_by_name?: string | null;
};

function defaultMonthBounds(): { from: string; to: string } {
  const now = new Date();
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth();
  const from = new Date(Date.UTC(year, month, 1));
  const to = new Date(Date.UTC(year, month + 1, 0));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

async function readDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string; error?: string };
    if (typeof body.detail === "string") return body.detail;
    if (typeof body.error === "string") return body.error;
  } catch {
    /* ignore */
  }
  return "";
}

export function PeriodClosePanel({ periods }: { periods: AccountingPeriodRow[] }) {
  const router = useRouter();
  const defaults = useMemo(() => defaultMonthBounds(), []);
  const [from, setFrom] = useState(defaults.from);
  const [to, setTo] = useState(defaults.to);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const closed = periods.filter((item) => item.status === "closed");

  async function closePeriod(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const res = await fetch("/api/backend/api/journal/periods/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from: from.trim(), to: to.trim() }),
      });
      if (!res.ok) {
        const detail = await readDetail(res);
        setError(detail || "No se pudo cerrar el período.");
        return;
      }
      setMessage("Período cerrado.");
      router.refresh();
    } catch {
      setError("No se pudo cerrar el período.");
    } finally {
      setBusy(false);
    }
  }

  async function reopenPeriod(dateFrom: string, dateTo: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const res = await fetch("/api/backend/api/journal/periods/reopen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from: dateFrom, to: dateTo }),
      });
      if (!res.ok) {
        const detail = await readDetail(res);
        setError(detail || "No se pudo reabrir el período.");
        return;
      }
      setMessage("Período reabierto.");
      router.refresh();
    } catch {
      setError("No se pudo reabrir el período.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.periodClose} aria-label="Cierre de período">
      <h2 className={styles.periodCloseTitle}>Cierre de período</h2>
      <p className={styles.periodCloseWarning}>
        Un período cerrado rechaza nuevos asientos (y reversos) con fecha en ese rango.
      </p>

      {closed.length > 0 ? (
        <ul className={styles.periodCloseList}>
          {closed.map((item) => (
            <li key={item.id}>
              <span>
                {item.from} → {item.to}
                {item.closed_by_name ? ` · ${item.closed_by_name}` : ""}
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void reopenPeriod(item.from, item.to)}
              >
                Reabrir
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.periodCloseEmpty}>No hay períodos cerrados.</p>
      )}

      <form className={styles.periodCloseForm} onSubmit={closePeriod}>
        <label>
          Desde
          <input
            type="date"
            name="from"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            required
          />
        </label>
        <label>
          Hasta
          <input
            type="date"
            name="to"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            required
          />
        </label>
        <div className={styles.filterActions}>
          <button type="submit" disabled={busy}>
            Cerrar período
          </button>
        </div>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="meta">{message}</p> : null}
    </section>
  );
}
