import styles from "./metrics.module.css";
import { SalesChart, type SalesDayPoint } from "./sales-chart";
import { TenderChart, type TenderSplit } from "./tender-chart";

export interface AnalyticsSeries {
  sales_by_day: SalesDayPoint[];
  tender: TenderSplit;
}

const EMPTY_TENDER: TenderSplit = { cash: "0.00", qr: "0.00" };

interface ChartsPanelProps {
  series?: AnalyticsSeries;
}

export function ChartsPanel({ series }: ChartsPanelProps) {
  const points = series?.sales_by_day ?? [];
  const tender = series?.tender ?? EMPTY_TENDER;

  return (
    <section className={styles.charts} aria-label="Gráficos del período">
      <SalesChart points={points} />
      <TenderChart tender={tender} />
    </section>
  );
}
