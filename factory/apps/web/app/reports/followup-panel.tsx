import Link from "next/link";

import styles from "./reports.module.css";
import { ReminderButton } from "./reminder-button";

export interface OverduePayment {
  id: string;
  provider_ref: string;
  amount: string;
  currency: string;
  status: string;
  status_label: string;
  order_id: string | null;
  order_label: string;
  customer_id: string;
  customer_label: string;
  overdue_days: number;
  href_open?: string | null;
}

export interface InactiveCustomer {
  id: string;
  name: string;
  wa_number: string;
  display_name: string;
  last_message_at: string;
  last_message_relative: string;
  inactive_days: number;
  conversation_id: string | null;
  href_open?: string | null;
}

export interface AlertsPayload {
  overdue_payments: OverduePayment[];
  inactive_customers: InactiveCustomer[];
  inactive_days: number;
}

interface FollowupPanelProps {
  alerts: AlertsPayload | null;
}

function money(amount: string): number {
  const parsed = Number(amount);
  return Number.isFinite(parsed) ? parsed : 0;
}

function bobSum(rows: OverduePayment[]): string {
  const total = rows.reduce((sum, row) => {
    if ((row.currency || "").toUpperCase() !== "BOB") return sum;
    return sum + money(row.amount);
  }, 0);
  return total.toFixed(2);
}

function daysAgo(days: number): string {
  if (days <= 0) return "hoy";
  if (days === 1) return "hace 1 día";
  return `hace ${days} días`;
}

function customerPrimary(row: InactiveCustomer): string {
  const display = (row.display_name || "").trim();
  if (display) return display;
  const phone = (row.wa_number || "").trim();
  if (phone) return phone;
  return (row.name || "").trim() || "Cliente";
}

function phoneSubtitle(row: InactiveCustomer): string | null {
  const phone = (row.wa_number || "").trim();
  if (!phone) return null;
  const primary = customerPrimary(row);
  if (primary === phone) return null;
  return phone;
}

function overdueOpenHref(row: OverduePayment): string {
  const fromApi = (row.href_open || "").trim();
  if (fromApi) return fromApi;
  const orderId = (row.order_id || "").trim();
  if (orderId) return `/orders?q=${encodeURIComponent(orderId)}`;
  return "/orders";
}

function inactiveOpenHref(row: InactiveCustomer): string {
  const fromApi = (row.href_open || "").trim();
  if (fromApi) return fromApi;
  const chatId = (row.conversation_id || "").trim();
  if (chatId) return `/chats/${encodeURIComponent(chatId)}`;
  const customerId = (row.id || "").trim();
  if (customerId) return `/customers/${encodeURIComponent(customerId)}`;
  return "/customers";
}

function overdueTitle(row: OverduePayment): string {
  const who = (row.customer_label || "").trim() || "Sin cliente";
  const order = (row.order_label || "").trim();
  if (order) return `${who} · ${order}`;
  return who;
}

export function FollowupPanel({ alerts }: FollowupPanelProps) {
  const overdue = alerts?.overdue_payments ?? [];
  const inactive = alerts?.inactive_customers ?? [];
  const inactiveDays = alerts?.inactive_days ?? inactive[0]?.inactive_days;

  return (
    <div className={styles.followup}>
      <section className={styles.followupSection} aria-labelledby="overdue-heading">
        <header className={styles.followupSectionHead}>
          <div>
            <p className={styles.followupJob}>1 · Cobrar</p>
            <h2 id="overdue-heading" className={styles.heading}>
              Pagos vencidos
            </h2>
            <p className={styles.hint}>
              QR o plazo vencido. Un aviso por WhatsApp no marca el pago como cobrado.
            </p>
          </div>
          <p className={styles.followupStat} aria-label="Resumen pagos vencidos">
            <strong>{overdue.length}</strong>
            <span>
              {overdue.length === 1 ? "pago" : "pagos"} · {bobSum(overdue)} BOB
            </span>
          </p>
        </header>

        {overdue.length === 0 ? (
          <p className={styles.followupEmpty}>Nada pendiente de cobro.</p>
        ) : (
          <ul className={styles.followupList}>
            {overdue.map((row) => {
              const canRemind = Boolean((row.customer_id || "").trim());
              return (
                <li key={row.id} className={styles.followupCard}>
                  <div className={styles.followupCardMain}>
                    <p className={styles.followupCardTitle}>{overdueTitle(row)}</p>
                    <p className={styles.followupCardMeta}>
                      <span className={styles.followupAmount}>
                        {row.amount} {row.currency}
                      </span>
                      <span aria-hidden>·</span>
                      <span>{daysAgo(row.overdue_days)}</span>
                      <span aria-hidden>·</span>
                      <span className={styles.followupBadge}>
                        {row.status_label || row.status}
                      </span>
                    </p>
                    {!canRemind ? (
                      <p className={styles.followupWarn}>
                        Sin cliente vinculado: podés abrir el pedido, pero no mandar aviso.
                      </p>
                    ) : null}
                  </div>
                  <div className={styles.followupCardActions}>
                    <Link className={styles.followupPrimary} href={overdueOpenHref(row)}>
                      Ver pedido
                    </Link>
                    {canRemind ? (
                      <ReminderButton customerId={row.customer_id} kind="collections" />
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className={styles.followupSection} aria-labelledby="inactive-heading">
        <header className={styles.followupSectionHead}>
          <div>
            <p className={styles.followupJob}>2 · Recontactar</p>
            <h2 id="inactive-heading" className={styles.heading}>
              Clientes quietos
            </h2>
            <p className={styles.hint}>
              {inactiveDays != null
                ? `Sin mensaje hace más de ${inactiveDays} días. El umbral se cambia en Analítica → Alertas.`
                : "Sin mensaje reciente. El umbral se cambia en Analítica → Alertas."}
            </p>
          </div>
          <p className={styles.followupStat} aria-label="Resumen clientes quietos">
            <strong>{inactive.length}</strong>
            <span>{inactive.length === 1 ? "cliente" : "clientes"}</span>
          </p>
        </header>

        {inactive.length === 0 ? (
          <p className={styles.followupEmpty}>Nadie en esta lista.</p>
        ) : (
          <ul className={styles.followupList}>
            {inactive.map((row) => {
              const phone = phoneSubtitle(row);
              return (
                <li key={row.id} className={styles.followupCard}>
                  <div className={styles.followupCardMain}>
                    <p className={styles.followupCardTitle}>{customerPrimary(row)}</p>
                    <p className={styles.followupCardMeta}>
                      {phone ? (
                        <>
                          <span>{phone}</span>
                          <span aria-hidden>·</span>
                        </>
                      ) : null}
                      <span>Último mensaje {row.last_message_relative}</span>
                    </p>
                  </div>
                  <div className={styles.followupCardActions}>
                    <Link className={styles.followupPrimary} href={inactiveOpenHref(row)}>
                      Abrir chat
                    </Link>
                    <ReminderButton customerId={row.id} />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
