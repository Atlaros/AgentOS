import styles from "./metrics.module.css";

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"] as const;

const FRAME = {
  width: 320,
  height: 132,
  padX: 10,
  padTop: 12,
  padBottom: 22,
} as const;

export interface SalesDayPoint {
  day: string;
  current: number;
  previous: number;
}

interface SalesChartProps {
  points: SalesDayPoint[];
}

interface PlotPoint {
  x: number;
  y: number;
}

function shortDay(iso: string): string {
  const parts = iso.split("-");
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  const name = MONTHS[month - 1] || parts[1] || "";
  if (!day) return iso;
  return `${day} ${name}`;
}

function plot(values: number[], max: number): PlotPoint[] {
  const innerW = FRAME.width - FRAME.padX * 2;
  const innerH = FRAME.height - FRAME.padTop - FRAME.padBottom;
  const step = values.length <= 1 ? 0 : innerW / (values.length - 1);
  return values.map((value, index) => {
    const x = FRAME.padX + step * index;
    const y = FRAME.padTop + innerH - (value / max) * innerH;
    return { x, y };
  });
}

function linePath(points: PlotPoint[]): string {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
}

function labelIndexes(length: number): number[] {
  if (length <= 1) return length === 1 ? [0] : [];
  if (length <= 4) return Array.from({ length }, (_, index) => index);
  return [0, Math.floor((length - 1) / 2), length - 1];
}

function anchorFor(index: number, last: number): "start" | "middle" | "end" {
  if (index <= 0) return "start";
  if (index >= last) return "end";
  return "middle";
}

export function SalesChart({ points }: SalesChartProps) {
  const quiet =
    points.length === 0 || points.every((point) => point.current === 0 && point.previous === 0);
  const peak = points.reduce((max, point) => Math.max(max, point.current, point.previous), 0);
  const scale = Math.max(peak, 1);
  const current = plot(
    points.map((point) => point.current),
    scale,
  );
  const previous = plot(
    points.map((point) => point.previous),
    scale,
  );
  const labels = labelIndexes(points.length);
  const baseline = FRAME.height - FRAME.padBottom;

  return (
    <article className={styles.chart}>
      <h2>Ventas por día</h2>
      {quiet ? (
        <p className={styles.chartEmpty}>Sin ventas en este período ni en el anterior.</p>
      ) : (
        <>
          <svg
            className={styles.chartSvg}
            viewBox={`0 0 ${FRAME.width} ${FRAME.height}`}
            role="img"
            aria-label="Ventas por día, este período y el anterior"
          >
            <line className={styles.axisLine} x1={FRAME.padX} y1={baseline} x2={FRAME.width - FRAME.padX} y2={baseline} />
            <path className={styles.linePrev} d={linePath(previous)} />
            <path className={styles.lineNow} d={linePath(current)} />
            {current.length === 1 ? <circle className={styles.lineNowDot} cx={current[0].x} cy={current[0].y} r={3} /> : null}
            {labels.map((index) => {
              const point = points[index];
              const spot = current[index];
              if (!point || !spot) return null;
              return (
                <text
                  key={point.day || String(index)}
                  className={styles.axis}
                  x={spot.x}
                  y={FRAME.height - 4}
                  textAnchor={anchorFor(index, points.length - 1)}
                >
                  {shortDay(point.day)}
                </text>
              );
            })}
          </svg>
          <p className={styles.legend}>
            <span className={styles.legendNow}>Este período</span>
            <span className={styles.legendPrev}>Anterior</span>
          </p>
        </>
      )}
    </article>
  );
}
