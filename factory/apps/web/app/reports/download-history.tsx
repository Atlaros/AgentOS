import styles from "./reports.module.css";

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

const REPORT_LABEL = {
  orders: "Ventas",
  payments: "Cobros",
  stock: "Inventario",
  package: "Paquete",
} as const;

type ReportId = keyof typeof REPORT_LABEL;

const PERIOD_LABEL = {
  today: "Hoy",
  "7d": "7 días",
  month: "Mes",
  range: "Rango",
} as const;

type PeriodKey = keyof typeof PERIOD_LABEL;

function isReportId(value: string): value is ReportId {
  return value in REPORT_LABEL;
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
  if (isReportId(reportId)) return REPORT_LABEL[reportId];
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

export function DownloadHistory({ rows }: { rows: DownloadRow[] }) {
  return (
    <section className={styles.history} aria-labelledby="download-history-heading">
      <h2 id="download-history-heading" className={styles.heading}>
        Descargas recientes
      </h2>
      <div className={styles.tableWrap}>
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Reporte</th>
              <th>Período</th>
              <th>Quién</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4}>Todavía no hay descargas.</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatStamp(row.created_at)}</td>
                  <td>{reportLabel(row.report_id)}</td>
                  <td>{periodLabel(row)}</td>
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
