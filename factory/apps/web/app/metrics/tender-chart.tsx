import styles from "./metrics.module.css";

const FRAME = {
  width: 220,
  height: 132,
  padTop: 18,
  padBottom: 28,
  bar: 36,
} as const;

export interface TenderSplit {
  cash: string;
  qr: string;
}

interface TenderChartProps {
  tender: TenderSplit;
}

function money(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function TenderChart({ tender }: TenderChartProps) {
  const cash = money(tender.cash);
  const qr = money(tender.qr);
  const quiet = cash === 0 && qr === 0;
  const scale = Math.max(cash, qr, 1);
  const innerH = FRAME.height - FRAME.padTop - FRAME.padBottom;
  const cashH = (cash / scale) * innerH;
  const qrH = (qr / scale) * innerH;
  const cashX = 48;
  const qrX = 128;
  const base = FRAME.height - FRAME.padBottom;

  return (
    <article className={styles.chart}>
      <h2>Efectivo y QR</h2>
      {quiet ? (
        <p className={styles.chartEmpty}>Sin ingresos de efectivo ni QR en este período.</p>
      ) : (
        <svg
          className={styles.chartSvg}
          viewBox={`0 0 ${FRAME.width} ${FRAME.height}`}
          role="img"
          aria-label={`Efectivo ${tender.cash} BOB, QR ${tender.qr} BOB`}
        >
          <line className={styles.axisLine} x1={24} y1={base} x2={FRAME.width - 16} y2={base} />
          <rect className={styles.barCash} x={cashX} y={base - cashH} width={FRAME.bar} height={Math.max(cashH, 0)} rx={3} />
          <rect className={styles.barQr} x={qrX} y={base - qrH} width={FRAME.bar} height={Math.max(qrH, 0)} rx={3} />
          <text className={styles.barValue} x={cashX + FRAME.bar / 2} y={base - cashH - 6} textAnchor="middle">
            {tender.cash}
          </text>
          <text className={styles.barValue} x={qrX + FRAME.bar / 2} y={base - qrH - 6} textAnchor="middle">
            {tender.qr}
          </text>
          <text className={styles.axis} x={cashX + FRAME.bar / 2} y={FRAME.height - 8} textAnchor="middle">
            Efectivo
          </text>
          <text className={styles.axis} x={qrX + FRAME.bar / 2} y={FRAME.height - 8} textAnchor="middle">
            QR
          </text>
        </svg>
      )}
    </article>
  );
}
