"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./ledger.module.css";

type LineDraft = {
  account_code: string;
  direction: string;
  amount: string;
};

const ACCOUNT_OPTIONS = [
  { value: "1100", label: "1100 Caja" },
  { value: "1200", label: "1200 Banco" },
  { value: "1300", label: "1300 Inventario" },
  { value: "1400", label: "1400 Cuentas por cobrar" },
  { value: "2100", label: "2100 Cuentas por pagar" },
  { value: "4100", label: "4100 Ventas" },
  { value: "5100", label: "5100 Gastos operativos" },
  { value: "5110", label: "5110 Costo de ventas" },
  { value: "5200", label: "5200 Retiros del dueño" },
] as const;

export function AdjustmentForm() {
  const router = useRouter();
  const [memo, setMemo] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([
    { account_code: "1300", direction: "debit", amount: "" },
    { account_code: "5100", direction: "credit", amount: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setOk("");
    try {
      const res = await fetch("/api/backend/api/journal/adjustments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          memo,
          lines: lines.map((line) => ({
            account_code: line.account_code,
            direction: line.direction,
            amount: line.amount,
          })),
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail || `Error ${res.status}`);
        return;
      }
      setOk("Asiento de ajuste registrado.");
      setMemo("");
      setLines([
        { account_code: "1300", direction: "debit", amount: "" },
        { account_code: "5100", direction: "credit", amount: "" },
      ]);
      router.refresh();
    } catch {
      setError("No se pudo registrar el ajuste.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.filtersForm} onSubmit={onSubmit} aria-label="Asiento de ajuste">
      <h2 className={styles.breakdownTitle}>Ajuste manual</h2>
      <p className="meta">
        Registrá un asiento manual equilibrado: la suma del Debe debe igualar la del Haber. El
        sistema no calcula IVA en este formulario; solo guarda el movimiento que indicás.
      </p>
      <label>
        Memo
        <input
          name="memo"
          value={memo}
          onChange={(event) => setMemo(event.target.value)}
          placeholder="Motivo del ajuste"
        />
      </label>
      {lines.map((line, index) => (
        <div key={index} className={styles.periodRow}>
          <label>
            Cuenta
            <select
              value={line.account_code}
              onChange={(event) => {
                const next = [...lines];
                next[index] = { ...line, account_code: event.target.value };
                setLines(next);
              }}
            >
              {ACCOUNT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Sentido
            <select
              value={line.direction}
              onChange={(event) => {
                const next = [...lines];
                next[index] = { ...line, direction: event.target.value };
                setLines(next);
              }}
            >
              <option value="debit">Debe</option>
              <option value="credit">Haber</option>
            </select>
          </label>
          <label>
            Monto
            <input
              value={line.amount}
              onChange={(event) => {
                const next = [...lines];
                next[index] = { ...line, amount: event.target.value };
                setLines(next);
              }}
              inputMode="decimal"
              required
            />
          </label>
        </div>
      ))}
      {error ? <p className="error">{error}</p> : null}
      {ok ? <p className="meta">{ok}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? "Guardando…" : "Registrar ajuste"}
      </button>
    </form>
  );
}
