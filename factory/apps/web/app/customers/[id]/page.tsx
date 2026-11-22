import Link from "next/link";
import { apiGet } from "@/lib/api";
import { NoteForm } from "../note-form";
import styles from "./customer-file.module.css";

type OrderItem = { name: string; quantity: number; unit_price: string };

type Delivery = { address: string; recipient_name: string };

type CustomerOrder = {
  id: string;
  public_number: string | null;
  status: string;
  items: OrderItem[];
  payment_status: string | null;
  discount?: string;
  total?: string;
  currency?: string;
  delivered_at: string | null;
  delivery: Delivery | null;
};

type CartLine = { name: string; quantity: number; unit_price: string; currency: string };

type CartView = {
  lines: CartLine[];
  total: string;
  currency: string;
} | null;

type CustomerChat = {
  id: string;
  message_count: number;
  last_text: string;
  human_takeover: boolean;
  needs_human: boolean;
  cart: CartView;
};

type CustomerFile = {
  id: string;
  name: string | null;
  wa_number: string;
  address: string | null;
  preferences: Record<string, string>;
  orders: CustomerOrder[];
  conversations: CustomerChat[];
  notes: { id: string; body: string; created_at?: string | null }[];
};

const PREF_LABELS: Record<string, string> = {
  color: "Color",
  size: "Talla",
  style: "Estilo",
  occasion: "Ocasión",
  budget_max: "Presupuesto",
};

function orderStateLabel(order: CustomerOrder): string {
  if (order.status === "delivered") return "Entregado";
  if (order.status === "cancelled") return "Cancelado";
  if (order.status === "placed" || (order.status === "open" && order.payment_status === "confirmed")) {
    return "Pedido";
  }
  return "Reserva";
}

function stateClass(label: string): string {
  if (label === "Entregado") return styles.done;
  if (label === "Cancelado") return styles.stop;
  if (label === "Pedido") return styles.live;
  return styles.hold;
}

function paymentLabel(status: string | null): string {
  if (status === "confirmed") return "Confirmado";
  if (status === "pending") return "Pendiente";
  if (status === "failed") return "Fallido";
  if (status === "expired") return "Vencido";
  if (status === "unknown") return "Sin confirmar";
  if (!status) return "Sin pago";
  return status;
}

function preferenceLabel(key: string): string {
  return PREF_LABELS[key] || key;
}

function filled(value: string | null | undefined): string {
  return (value || "").trim();
}

function deliveryLine(delivery: Delivery | null): string | null {
  if (!delivery) return null;
  const name = filled(delivery.recipient_name);
  const address = filled(delivery.address);
  if (name && address) return `${name} · ${address}`;
  return name || address || null;
}

function cartSummary(cart: CartView): string | null {
  if (!cart || cart.lines.length === 0) return null;
  const lines = cart.lines.map((line) => `${line.name} ×${line.quantity}`).join(", ");
  return `${lines} · ${cart.total} ${cart.currency}`;
}

function when(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("es-BO");
}

export default async function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let file: CustomerFile | null = null;
  let error = "";
  try {
    file = await apiGet<CustomerFile>(`/api/customers/${id}`);
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  const title = file ? filled(file.name) || "Sin nombre" : "Cliente";
  const preferences = Object.entries(file?.preferences || {});

  return (
    <div className={styles.file}>
      <p className={styles.back}>
        <Link href="/customers">Clientes</Link>
      </p>
      <header className={styles.header}>
        <h1 className={styles.title}>{title}</h1>
        {file ? <p className={styles.wa}>{file.wa_number}</p> : null}
      </header>
      {error ? <p className="error">{error}</p> : null}
      {file ? (
        <>
          <section className={styles.section} aria-labelledby="perfil">
            <h2 id="perfil" className={styles.kicker}>
              Perfil
            </h2>
            <dl className={styles.facts}>
              <dt>Nombre</dt>
              <dd className={filled(file.name) ? undefined : styles.missing}>
                {filled(file.name) || "Sin nombre"}
              </dd>
              <dt>WhatsApp</dt>
              <dd>{file.wa_number}</dd>
              <dt>Dirección</dt>
              <dd className={filled(file.address) ? undefined : styles.missing}>
                {filled(file.address) || "Sin dirección"}
              </dd>
            </dl>
          </section>

          <section className={styles.section} aria-labelledby="preferencias">
            <h2 id="preferencias" className={styles.kicker}>
              Preferencias
            </h2>
            {preferences.length === 0 ? (
              <p className={styles.empty}>Sin preferencias guardadas.</p>
            ) : (
              <dl className={styles.prefs}>
                {preferences.map(([key, value]) => (
                  <div key={key} className={styles.prefRow}>
                    <dt className={styles.prefKey}>{preferenceLabel(key)}</dt>
                    <dd className={styles.prefValue}>{value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>

          <section className={styles.section} aria-labelledby="pedidos">
            <h2 id="pedidos" className={styles.kicker}>
              Pedidos / compras
            </h2>
            {file.orders.length === 0 ? <p className={styles.empty}>Sin pedidos.</p> : null}
            <div className={styles.tickets}>
              {file.orders.map((order) => {
                const label = orderStateLabel(order);
                const sent = deliveryLine(order.delivery);
                const delivered = when(order.delivered_at);
                const discount = Number(order.discount || 0);
                return (
                  <article key={order.id} className={styles.ticket}>
                    <div className={styles.ticketHead}>
                      <span className={styles.ticketNo}>
                        <code>{order.public_number || order.id.slice(0, 8)}</code>
                      </span>
                      <span className={styles.total}>
                        {order.total ? `${order.total} ${order.currency || "BOB"}` : "—"}
                      </span>
                    </div>
                    <p className={styles.statusLine}>
                      <span className={`${styles.state} ${stateClass(label)}`}>{label}</span>
                      <span>{paymentLabel(order.payment_status)}</span>
                      {delivered ? <span>{delivered}</span> : null}
                    </p>
                    <p className={styles.lines}>
                      {order.items.map((item) => `${item.name} ×${item.quantity}`).join("; ") || "Sin productos"}
                    </p>
                    {discount > 0 ? (
                      <p className={styles.statusLine}>
                        Descuento {order.discount} {order.currency || "BOB"}
                      </p>
                    ) : null}
                    {sent ? <p className={styles.delivery}>Entrega: {sent}</p> : null}
                  </article>
                );
              })}
            </div>
          </section>

          <section className={styles.section} aria-labelledby="actividad">
            <h2 id="actividad" className={styles.kicker}>
              Actividad con el agente
            </h2>
            {file.conversations.length === 0 ? (
              <p className={styles.empty}>Sin actividad con el agente.</p>
            ) : (
              <div className={styles.activity}>
                {file.conversations.map((conv) => {
                  const cart = cartSummary(conv.cart);
                  return (
                    <article key={conv.id} className={styles.chat}>
                      <div className={styles.chatHead}>
                        <Link className={styles.chatLink} href={`/chats/${conv.id}`}>
                          {conv.message_count} {conv.message_count === 1 ? "mensaje" : "mensajes"}
                        </Link>
                        {conv.human_takeover ? <span className={`${styles.badge} ${styles.pause}`}>Agente pausado</span> : null}
                        {conv.needs_human ? <span className={`${styles.badge} ${styles.human}`}>Necesita humano</span> : null}
                      </div>
                      <p className={styles.last}>{filled(conv.last_text) || "Sin texto"}</p>
                      {cart ? <p className={styles.cart}>Carrito: {cart}</p> : null}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <section className={styles.section} aria-labelledby="notas">
            <h2 id="notas" className={styles.kicker}>
              Notas
            </h2>
            <NoteForm customerId={file.id} />
            {file.notes.length === 0 ? <p className={styles.empty}>Sin notas.</p> : null}
            <ul className={styles.notes}>
              {file.notes.map((note) => {
                const stamp = when(note.created_at);
                return (
                  <li key={note.id} className={styles.note}>
                    {note.body}
                    {stamp ? <time dateTime={note.created_at || undefined}>{stamp}</time> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}
