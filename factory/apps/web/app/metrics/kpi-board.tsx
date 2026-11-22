import Link from "next/link";

import styles from "./metrics.module.css";

const KPI_KIND = {
  MONEY: "money",
  COUNT: "count",
} as const;

type KpiKind = (typeof KPI_KIND)[keyof typeof KPI_KIND];

const UNAVAILABLE = {
  MISSING_COSTS: "missing_costs",
} as const;

export interface RevenueBreakdown {
  cash: string;
  qr: string;
}

export interface Kpi {
  id: string;
  label: string;
  kind: KpiKind;
  current: string | number | null;
  previous: string | number | null;
  pct_change: number | null;
  previous_empty: boolean;
  current_empty: boolean;
  unavailable_reason?: string;
}

const EMPTY_COPY: Record<string, string> = {
  revenue: "Sin ingresos confirmados en este período.",
  sales: "Sin ventas confirmadas en este período.",
  avg_ticket: "Sin ventas para calcular el ticket.",
  purchases: "Sin compras recibidas en este período.",
  profit: "Sin utilidad en este período.",
};

const KPI_HREF: Record<string, string> = {
  purchases: "/suppliers?tab=ordenes",
};

const DELTA_TONE = {
  up: "deltaUp",
  down: "deltaDown",
  flat: "delta",
} as const;

type DeltaTone = (typeof DELTA_TONE)[keyof typeof DELTA_TONE];

interface DeltaView {
  text: string;
  tone: DeltaTone;
}

interface KpiBoardProps {
  kpis: Kpi[];
  revenueBreakdown?: RevenueBreakdown;
}

function deltaView(kpi: Kpi): DeltaView | null {
  if (kpi.pct_change === null || kpi.previous_empty) return null;
  const rounded = Math.round(kpi.pct_change * 10) / 10;
  const abs = Math.abs(rounded).toLocaleString("es-BO", { maximumFractionDigits: 1 });
  if (rounded > 0) return { text: `↑ ${abs}%`, tone: DELTA_TONE.up };
  if (rounded < 0) return { text: `↓ ${abs}%`, tone: DELTA_TONE.down };
  return { text: "0%", tone: DELTA_TONE.flat };
}

function missingCosts(kpi: Kpi): boolean {
  return kpi.unavailable_reason === UNAVAILABLE.MISSING_COSTS;
}

function currentText(kpi: Kpi): string {
  if (missingCosts(kpi)) return "Falta registrar costos";
  if (kpi.current == null) return "—";
  if (kpi.kind === KPI_KIND.MONEY) return `${kpi.current} BOB`;
  return String(kpi.current);
}

export function KpiBoard({ kpis, revenueBreakdown }: KpiBoardProps) {
  if (kpis.length === 0) {
    return <p className={styles.emptyNote}>No hay indicadores para este período.</p>;
  }

  return (
    <ul className={styles.kpiGrid}>
      {kpis.map((kpi) => {
        const href = KPI_HREF[kpi.id];
        const delta = deltaView(kpi);
        const sentence = missingCosts(kpi);
        const body = (
          <>
                <span className={styles.kpiLabel}>{kpi.label}</span>
            <strong className={sentence ? styles.unavailable : styles.figure}>{currentText(kpi)}</strong>
            {kpi.id === "revenue" && revenueBreakdown && !kpi.current_empty ? (
              <span className={styles.split}>
                Efectivo {revenueBreakdown.cash} · QR {revenueBreakdown.qr}
              </span>
            ) : null}
            {delta ? <span className={styles[delta.tone]}>{delta.text}</span> : null}
            {kpi.current_empty && !sentence ? (
              <span className={styles.empty}>{EMPTY_COPY[kpi.id] || "Sin datos en este período."}</span>
            ) : null}
          </>
        );
        return (
          <li key={kpi.id}>
            {href ? (
              <Link className={styles.cardLink} href={href}>
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ul>
  );
}
