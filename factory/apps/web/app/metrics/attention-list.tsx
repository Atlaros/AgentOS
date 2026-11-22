import Link from "next/link";

import styles from "./metrics.module.css";

const SEVERITY = {
  low_stock: "warn",
  payment_overdue: "danger",
  customer_inactive: "warn",
  qr_pending_stale: "warn",
  zero_stock_sales: "danger",
} as const;

const FOLLOWUP_HREF = "/reports?tab=seguimiento";

const ACTION = {
  low_stock: "Ver reposición",
  payment_overdue: "Ver seguimiento",
  customer_inactive: "Ver seguimiento",
  qr_pending_stale: "Ver pedidos",
  zero_stock_sales: "Ver reposición",
} as const;

type AlertType = keyof typeof ACTION;
type Severity = (typeof SEVERITY)[keyof typeof SEVERITY];

export type AttentionAlert = {
  type: string;
  count: number;
  href: string;
  label: string;
};

type AttentionListProps = {
  alerts: AttentionAlert[];
  hours: number;
  days: number;
};

function isAlertType(value: string): value is AlertType {
  return value in ACTION;
}

function attentionHref(alert: AttentionAlert): string {
  if (alert.type === "payment_overdue" || alert.type === "customer_inactive") {
    return FOLLOWUP_HREF;
  }
  if (typeof alert.href === "string" && alert.href.trim()) {
    return alert.href;
  }
  if (alert.type === "low_stock" || alert.type === "zero_stock_sales") {
    return "/suppliers?tab=reposicion";
  }
  if (alert.type === "qr_pending_stale") {
    return "/orders";
  }
  return "/reports";
}

function attentionCopy(alert: AttentionAlert, hours: number, days: number): string {
  const count = alert.count;
  if (alert.type === "low_stock") {
    const noun = count === 1 ? "variante" : "variantes";
    return `${count} ${noun} con stock bajo`;
  }
  if (alert.type === "payment_overdue") {
    return count === 1 ? "1 pago vencido" : `${count} pagos vencidos`;
  }
  if (alert.type === "customer_inactive") {
    const noun = count === 1 ? "cliente inactivo" : "clientes inactivos";
    return `${count} ${noun} hace más de ${days} días`;
  }
  if (alert.type === "qr_pending_stale") {
    if (count === 1) return `QR pendiente hace más de ${hours} h`;
    return `${count} QR pendientes hace más de ${hours} h`;
  }
  if (alert.type === "zero_stock_sales") {
    return count === 1 ? "Venta con stock en 0" : `${count} ventas con stock en 0`;
  }
  return `${alert.label}: ${count}`;
}

export function AttentionList({ alerts, hours, days }: AttentionListProps) {
  return (
    <section className={styles.attention} aria-label="Requiere atención">
      <h2>Requiere atención</h2>
      {alerts.length === 0 ? (
        <p className={styles.emptyNote}>Sin alertas activas.</p>
      ) : (
        <ul className={styles.attentionList}>
          {alerts.map((alert) => {
            const alertType = alert.type;
            const level: Severity = isAlertType(alertType) ? SEVERITY[alertType] : "warn";
            const action = isAlertType(alertType) ? ACTION[alertType] : "Abrir";
            return (
              <li key={alert.type} className={styles.attentionRow}>
                <span className={styles.severity} data-level={level} aria-hidden="true" />
                <span className={styles.attentionCopy}>{attentionCopy(alert, hours, days)}</span>
                <Link href={attentionHref(alert)}>{action}</Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
