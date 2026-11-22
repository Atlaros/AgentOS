import { apiGet } from "@/lib/api";

import { DownloadHistory, type DownloadRow } from "./download-history";
import { DownloadsPanel, type ReportCard, type ReportFormat } from "./downloads-panel";
import { FollowupPanel, type AlertsPayload } from "./followup-panel";
import { PeriodToolbar } from "./period-toolbar";
import { ReportsTabs, resolveReportTab } from "./reports-tabs";
import styles from "./reports.module.css";

type ReportsQuery = {
  tab?: string | string[];
  period?: string | string[];
  date_from?: string | string[];
  date_to?: string | string[];
  format?: string | string[];
};

type ReportsPageProps = {
  searchParams: Promise<ReportsQuery>;
};

const PERIOD = {
  TODAY: "today",
  WEEK: "7d",
  MONTH: "month",
  RANGE: "range",
} as const;

type PeriodId = (typeof PERIOD)[keyof typeof PERIOD];

const REPORT_FORMAT = {
  CSV: "csv",
  XLSX: "xlsx",
} as const;

interface ReportCatalog {
  reports: ReportCard[];
  excel_available?: boolean;
}

interface DownloadHistoryBody {
  downloads: DownloadRow[];
}

function readQuery(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw || "").trim();
}

function isPeriodId(value: string): value is PeriodId {
  return (
    value === PERIOD.TODAY ||
    value === PERIOD.WEEK ||
    value === PERIOD.MONTH ||
    value === PERIOD.RANGE
  );
}

function isReportFormat(value: string): value is ReportFormat {
  return value === REPORT_FORMAT.CSV || value === REPORT_FORMAT.XLSX;
}

function packageHref(format: ReportFormat): string {
  const params = new URLSearchParams({ period: PERIOD.MONTH, format });
  return `/api/backend/api/reports/package?${params.toString()}`;
}

function accountingPackageHref(): string {
  const params = new URLSearchParams({ period: PERIOD.MONTH, format: REPORT_FORMAT.XLSX });
  return `/api/backend/api/reports/accounting-package?${params.toString()}`;
}

async function DownloadsSection({
  period,
  dateFrom,
  dateTo,
  ready,
  requestedFormat,
}: {
  period: PeriodId;
  dateFrom: string;
  dateTo: string;
  ready: boolean;
  requestedFormat: ReportFormat;
}) {
  let cards: ReportCard[] = [];
  let error = "";
  let excelAvailable = false;
  if (ready) {
    const query = new URLSearchParams({ period });
    if (period === PERIOD.RANGE) {
      query.set("date_from", dateFrom);
      query.set("date_to", dateTo);
    }
    try {
      const body = await apiGet<ReportCatalog>(`/api/reports/catalog?${query.toString()}`);
      cards = body.reports || [];
      excelAvailable = Boolean(body.excel_available);
    } catch (err) {
      error = err instanceof Error ? err.message : "error";
    }
  }
  const format: ReportFormat =
    requestedFormat === REPORT_FORMAT.XLSX && excelAvailable ? REPORT_FORMAT.XLSX : REPORT_FORMAT.CSV;

  let history: DownloadRow[] = [];
  let historyError = "";
  try {
    const body = await apiGet<DownloadHistoryBody>("/api/reports/downloads/history");
    history = body.downloads || [];
  } catch (err) {
    historyError = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <PeriodToolbar
        active={period}
        dateFrom={dateFrom}
        dateTo={dateTo}
        format={format}
        excelAvailable={excelAvailable}
      />
      {period === PERIOD.RANGE && !ready ? (
        <p className="meta">Elegí desde y hasta para ver cuántas filas entran.</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <div className={styles.packageRow}>
        <a className={styles.packageCard} href={packageHref(format)}>
          <span className={styles.packageTitle}>Paquete operativo del mes</span>
          <span className={styles.packageMeta}>Ventas, cobros e inventario en un Excel</span>
        </a>
        <a className={styles.packageCard} href={accountingPackageHref()}>
          <span className={styles.packageTitle}>Paquete contable del mes</span>
          <span className={styles.packageMeta}>
            Diario, mayor y más (mismo dato que Contabilidad)
          </span>
        </a>
      </div>
      <DownloadsPanel cards={cards} format={format} />
      {historyError ? <p className="error">{historyError}</p> : null}
      <DownloadHistory rows={history} />
    </>
  );
}

async function FollowupSection() {
  let alerts: AlertsPayload | null = null;
  let error = "";
  try {
    alerts = await apiGet<AlertsPayload>("/api/alerts");
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <FollowupPanel alerts={alerts} />
    </>
  );
}

export default async function ReportsPage({ searchParams }: ReportsPageProps) {
  const params = await searchParams;
  const activeTab = resolveReportTab(readQuery(params.tab));
  const requested = readQuery(params.period);
  const period: PeriodId = isPeriodId(requested) ? requested : PERIOD.WEEK;
  const dateFrom = readQuery(params.date_from);
  const dateTo = readQuery(params.date_to);
  const requestedFormatRaw = readQuery(params.format);
  const requestedFormat: ReportFormat = isReportFormat(requestedFormatRaw)
    ? requestedFormatRaw
    : REPORT_FORMAT.CSV;
  const rangeReady = period !== PERIOD.RANGE || Boolean(dateFrom && dateTo);

  const tabLead =
    activeTab === "descargas"
      ? "Acá bajás archivos del período (Excel/CSV). Para ver el libro día a día usá Contabilidad."
      : "Dos listas: a quién cobrar, y a quién escribir de nuevo.";

  return (
    <>
      <h1>Reportes</h1>
      <p className={styles.pageKicker}>
        {activeTab === "descargas" ? "Descargas" : "Seguimiento"}
      </p>
      <p className={`lead ${styles.pageLead}`}>{tabLead}</p>
      <ReportsTabs activeTab={activeTab} />
      {activeTab === "descargas" ? (
        <DownloadsSection
          period={period}
          dateFrom={dateFrom}
          dateTo={dateTo}
          ready={rangeReady}
          requestedFormat={requestedFormat}
        />
      ) : (
        <FollowupSection />
      )}
    </>
  );
}
