"use client";

import { useEffect, useState } from "react";

import styles from "./ledger.module.css";

export interface DownloadRow {
  id: string;
  report_id: string;
  period_id: string;
  date_from: string | null;
  date_to: string | null;
  format: string;
  actor_name: string;
  created_at: string | null;
}

const LEDGER_REPORT_IDS = {
  journal: "Diario",
  ledger_hechos: "Hechos",
  mayor: "Mayor",
  resultado: "Resultado",
  balance: "Balance",
  comprobacion: "Comprobación",
  conciliacion: "Conciliación",
} as const;

type LedgerReportId = keyof typeof LEDGER_REPORT_IDS;

const PERIOD_LABEL = {
  today: "Hoy",
  week: "Semana",
  month: "Mes",
  "7d": "7 días",
  range: "Rango",
} as const;

type PeriodKey = keyof typeof PERIOD_LABEL;

function isLedgerReportId(value: string): value is LedgerReportId {
  return value in LEDGER_REPORT_IDS;
}

function isPeriodKey(value: string): value is PeriodKey {
  return value in PERIOD_LABEL;
}

function formatStamp(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("es-BO", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function reportLabel(reportId: string): string {
  if (isLedgerReportId(reportId)) return LEDGER_REPORT_IDS[reportId];
  return reportId;
}

function periodLabel(row: DownloadRow): string {
  if (isPeriodKey(row.period_id)) {
    if (row.period_id === "range" && row.date_from && row.date_to) {
      return `${row.date_from.slice(0, 10)} – ${row.date_to.slice(0, 10)}`;
    }
    return PERIOD_LABEL[row.period_id];
  }
  if (/^\d{4}-\d{2}$/.test(row.period_id)) return row.period_id;
  if (!row.period_id) return "Todo";
  return row.period_id;
}

function formatLabel(format: string): string {
  const value = format.trim().toLowerCase();
  if (value === "xlsx") return "Excel";
  if (value === "csv") return "CSV";
  if (value === "pdf") return "PDF";
  return format || "—";
}

export function LedgerDownloadHistory() {
  const [rows, setRows] = useState<DownloadRow[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backend/api/reports/downloads/history", { cache: "no-store" })
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 403 || res.status === 401) {
          setRows(null);
          return;
        }
        if (!res.ok) {
          setRows([]);
          return;
        }
        const body = (await res.json()) as { downloads?: DownloadRow[] };
        const all = body.downloads || [];
        setRows(all.filter((row) => isLedgerReportId(row.report_id)));
      })
      .catch(() => {
        if (!cancelled) setRows(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (rows === null) return null;

  return (
    <section className={styles.history} aria-labelledby="ledger-download-history-heading">
      <h2 id="ledger-download-history-heading" className={styles.historyHeading}>
        Historial de descargas
      </h2>
      <div className={styles.historyTableWrap}>
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Reporte</th>
              <th>Período</th>
              <th>Formato</th>
              <th>Quién</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5}>Todavía no hay descargas contables.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatStamp(row.created_at)}</td>
                  <td>{reportLabel(row.report_id)}</td>
                  <td>{periodLabel(row)}</td>
                  <td>{formatLabel(row.format)}</td>
                  <td>{row.actor_name || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
