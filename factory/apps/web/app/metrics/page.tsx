import { apiGet } from "@/lib/api";

import styles from "./metrics.module.css";
import { AskAnalyst } from "./ask-analyst";
import { AttentionList } from "./attention-list";
import { BoardLayout } from "./board-layout";
import { ChartsPanel, type AnalyticsSeries } from "./charts-panel";
import { InfoTip } from "./info-tip";
import { KpiBoard, type Kpi, type RevenueBreakdown } from "./kpi-board";
import { PeriodToolbar } from "./period-toolbar";
import type { ThresholdValues } from "./thresholds-form";

type PeriodWindow = {
  id: string;
  basis: string;
  start: string;
  end: string;
  previous_start: string;
  previous_end: string;
  previous_end_inclusive?: string;
  label_current?: string;
  label_previous?: string;
};

interface Summary {
  period: PeriodWindow;
  kpis: Kpi[];
  alerts: AttentionAlert[];
  alert_type_count: number;
  revenue_breakdown?: RevenueBreakdown;
  series?: AnalyticsSeries;
}

type AttentionAlert = {
  type: string;
  count: number;
  href: string;
  label: string;
};

const PERIOD = {
  TODAY: "today",
  WEEK: "7d",
  MONTH: "month",
  RANGE: "range",
} as const;

const LEAD =
  "Comparación del período contra el tramo anterior de la misma duración. Los ingresos suman cobros confirmados y ventas de caja registradas; lo anulado no entra.";

const WEEK_NOTE = "Los 7 días son una ventana corrida de 7×24 horas.";

const DEFAULT_QR_HOURS = 24;
const DEFAULT_INACTIVE_DAYS = 30;

type MetricsPageProps = {
  searchParams: Promise<MetricsQuery>;
};

type MetricsQuery = {
  period?: string | string[];
  date_from?: string | string[];
  date_to?: string | string[];
};

function readQuery(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

function datePart(iso: string): string {
  return iso.slice(0, 10);
}

function formatStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("es-BO", {
    day: "numeric",
    month: "short",
    timeZone: "America/La_Paz",
  }).format(date);
}

function comparisonText(period: PeriodWindow): string {
  if (period.label_current && period.label_previous) {
    return `${period.label_current} frente a ${period.label_previous}`;
  }
  const previousClose = period.previous_end_inclusive || period.previous_end;
  const currentClose = new Date(period.end);
  if (!Number.isNaN(currentClose.getTime())) {
    currentClose.setTime(currentClose.getTime() - 1);
  }
  const currentEnd = Number.isNaN(currentClose.getTime())
    ? formatStamp(period.end)
    : formatStamp(currentClose.toISOString());
  return `${formatStamp(period.start)} – ${currentEnd} frente a ${formatStamp(period.previous_start)} – ${formatStamp(previousClose)}`;
}

function knownPeriod(value: string): boolean {
  return value === PERIOD.TODAY || value === PERIOD.WEEK || value === PERIOD.MONTH || value === PERIOD.RANGE;
}

export default async function MetricsPage({ searchParams }: MetricsPageProps) {
  const params = await searchParams;
  const requested = readQuery(params.period);
  const dateFrom = readQuery(params.date_from);
  const dateTo = readQuery(params.date_to);
  const period = knownPeriod(requested) ? requested : PERIOD.WEEK;
  const rangeReady = period === PERIOD.RANGE && Boolean(dateFrom) && Boolean(dateTo);
  const fetchPeriod = period === PERIOD.RANGE && !rangeReady ? PERIOD.WEEK : period;
  const query = new URLSearchParams({ period: fetchPeriod });
  if (fetchPeriod === PERIOD.RANGE) {
    query.set("date_from", dateFrom);
    query.set("date_to", dateTo);
  }

  let data: Summary | null = null;
  let thresholds: ThresholdValues | null = null;
  let error = "";
  try {
    data = await apiGet<Summary>(`/api/metrics?${query.toString()}`);
  } catch (err) {
    const message = err instanceof Error ? err.message : "error";
    error = message.startsWith("403")
      ? "Analítica es para el dueño y el supervisor."
      : "No se pudo cargar Analítica.";
  }
  if (!error) {
    try {
      thresholds = await apiGet<ThresholdValues>("/api/analytics/thresholds");
    } catch {
      thresholds = null;
    }
  }

  const active = data?.period.id || fetchPeriod;
  const compareMissing = Boolean(data && data.kpis.length > 0 && data.kpis.every((kpi) => kpi.previous_empty));
  const hours = thresholds?.qr_pending_hours ?? DEFAULT_QR_HOURS;
  const days = thresholds?.inactive_days ?? DEFAULT_INACTIVE_DAYS;

  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <BoardLayout
        main={
          <>
            <header className={styles.header}>
              <h1>Analítica</h1>
              <InfoTip label="Cómo se lee este tablero" text={LEAD} />
            </header>
            <PeriodToolbar
              active={active}
              explicit={Boolean(requested)}
              from={dateFrom ? datePart(dateFrom) : ""}
              to={dateTo ? datePart(shiftExclusive(dateTo)) : ""}
              dateFrom={dateFrom}
              dateTo={dateTo}
              canEdit={Boolean(thresholds?.can_edit)}
              thresholds={thresholds}
            />
            {data ? (
              <p className={styles.window}>
                <span>{comparisonText(data.period)}</span>
                {active === PERIOD.WEEK ? (
                  <InfoTip label="Cómo se cuentan los 7 días" text={WEEK_NOTE} />
                ) : null}
              </p>
            ) : null}
            {compareMissing ? (
              <p className={styles.banner}>Aún no hay datos del período anterior para comparar.</p>
            ) : null}
            {data ? (
              <KpiBoard kpis={data.kpis} revenueBreakdown={data.revenue_breakdown} />
            ) : error ? (
              <p className={styles.emptyNote}>No se pudieron cargar los indicadores.</p>
            ) : null}
            {data ? <AttentionList alerts={data.alerts} hours={hours} days={days} /> : null}
            {data ? (
              <ChartsPanel series={data.series} />
            ) : error ? (
              <p className={styles.emptyNote}>No se pudieron cargar los gráficos.</p>
            ) : null}
          </>
        }
        aside={
          error ? (
            <p className={styles.emptyNote}>El Analista espera a que cargue el tablero.</p>
          ) : (
            <AskAnalyst period={fetchPeriod} />
          )
        }
      />
    </>
  );
}

function shiftExclusive(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString();
}
