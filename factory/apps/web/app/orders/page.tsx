import Link from "next/link";
import { revalidatePath } from "next/cache";

import { OpenableProductThumb } from "@/components/openable-product-thumb";
import { apiGet, apiPost } from "@/lib/api";

import { DeliveryForm } from "./delivery-form";
import { ManualOrderForm, type CatalogOption } from "./manual-order-form";
import { OrderEditForm } from "./order-edit-form";
import { OrdersSearch } from "./orders-search";
import styles from "./orders.module.css";

type OrderItem = {
  variant_sku: string;
  name: string;
  unit_price: string;
  currency: string;
  quantity: number;
  media_id?: string;
  thumb_url?: string;
  image_url?: string;
};

type OrderRow = {
  id: string;
  public_number: string | null;
  status: string;
  payment_status: string | null;
  provider?: string | null;
  delivered_at: string | null;
  customer_name: string | null;
  customer_address?: string | null;
  wa_number: string;
  location: string | null;
  has_delivery?: boolean;
  delivery?: { address: string; recipient_name: string } | null;
  items: OrderItem[];
  discount?: string;
  total?: string;
  hold_minutes?: number;
};

type OrdersPageProps = {
  searchParams: Promise<{ q?: string | string[]; delivery?: string | string[]; edit?: string | string[] }>;
};

async function markDelivered(orderId: string) {
  "use server";
  await apiPost(`/api/orders/${orderId}/delivered`);
  revalidatePath("/orders");
  revalidatePath("/catalog");
}

async function setStatus(orderId: string, status: string) {
  "use server";
  await apiPost(`/api/orders/${orderId}/status`, { status });
  revalidatePath("/orders");
  revalidatePath("/catalog");
}

function orderStateLabel(order: OrderRow): string {
  if (order.status === "delivered") return "Entregado";
  if (order.status === "cancelled") return "Cancelado";
  if (
    order.status === "placed" ||
    (order.status === "open" && order.payment_status === "confirmed")
  ) {
    return "Pedido";
  }
  return "Reserva";
}

function readQuery(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw || "").trim();
}

function orderLabel(order: OrderRow): string {
  const number = order.public_number || order.id.slice(0, 8);
  const who = order.customer_name || order.wa_number || "sin cliente";
  return `${number} · ${who}`;
}

function withParams(q: string, extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  for (const [key, value] of Object.entries(extra || {})) {
    if (value) params.set(key, value);
  }
  const query = params.toString();
  return query ? `/orders?${query}` : "/orders";
}

function paymentLabel(order: OrderRow): string {
  if (order.provider === "cash" && order.payment_status === "confirmed") return "Caja";
  if (order.payment_status === "confirmed") return "Confirmado";
  if (order.payment_status === "pending") return "Pendiente";
  return order.payment_status || "—";
}

export default async function OrdersPage({ searchParams }: OrdersPageProps) {
  const params = await searchParams;
  const q = readQuery(params.q);
  const deliveryFocus = readQuery(params.delivery);
  const editFocus = readQuery(params.edit);
  const path = q ? `/api/orders?${new URLSearchParams({ q }).toString()}` : "/api/orders";
  let orders: OrderRow[] = [];
  let allOrders: OrderRow[] = [];
  let products: CatalogOption[] = [];
  let error = "";
  try {
    const data = await apiGet<{ orders: OrderRow[] }>(path);
    orders = data.orders;
    allOrders = q ? (await apiGet<{ orders: OrderRow[] }>("/api/orders")).orders : orders;
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  try {
    const catalog = await apiGet<{ products: CatalogOption[] }>("/api/catalog?limit=200");
    products = catalog.products;
  } catch (err) {
    if (!error) error = err instanceof Error ? err.message : "error";
  }

  const editing = allOrders.find((order) => order.id === editFocus) ?? null;

  const candidates = allOrders
    .filter((order) => order.payment_status === "confirmed" && !order.has_delivery)
    .map((order) => ({
      id: order.id,
      label: orderLabel(order),
      location: order.location || "",
    }));

  return (
    <>
      <h1>Pedidos</h1>
      <p className="lead">
        {orders.filter((o) => o.status === "reserved" || (o.status === "open" && o.payment_status !== "confirmed")).length}{" "}
        reservas
        {" · "}
        {
          orders.filter(
            (o) =>
              o.status === "placed" ||
              o.status === "delivered" ||
              (o.status === "open" && o.payment_status === "confirmed"),
          ).length
        }{" "}
        pedidos
        {" · "}
        {orders.filter((o) => o.payment_status === "pending").length} con QR pendiente. Con código de
        live la reserva vence a los 15 minutos; sin código, a los 20.
      </p>
      <OrdersSearch q={q} />
      <ManualOrderForm products={products} />
      {editing ? (
        <OrderEditForm order={editing} products={products} closeHref={withParams(q)} />
      ) : null}
      <DeliveryForm candidates={candidates} initialOrderId={deliveryFocus} />
      <p className={`meta ${styles.hint}`}>
        {q ? `${orders.length} coincidencias para «${q}». ` : null}
        La tabla es para consultar. El pedido de caja se carga arriba; la entrega manual queda
        debajo y solo escribe si el pago ya está confirmado.
      </p>
      {error ? <p className="error">{error}</p> : null}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nº</th>
              <th>Cliente</th>
              <th>Ubicación</th>
              <th>Estado</th>
              <th>Pago</th>
              <th>Entrega</th>
              <th>Prendas</th>
              <th>Total</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>
                  <code>{o.public_number || o.id.slice(0, 8)}</code>
                </td>
                <td>
                  {o.customer_name || "Sin nombre"}
                  <div className="meta">{o.wa_number || "—"}</div>
                </td>
                <td>
                  {o.delivery ? (
                    <>
                      <div className={styles.recipient}>{o.delivery.recipient_name}</div>
                      <div className="meta">{o.delivery.address}</div>
                    </>
                  ) : (
                    o.location || "Sin ubicación"
                  )}
                </td>
                <td>{orderStateLabel(o)}</td>
                <td>{paymentLabel(o)}</td>
                <td>
                  {o.delivered_at ? new Date(o.delivered_at).toLocaleString("es-BO") : "Pendiente"}
                </td>
                <td>
                  <ul className={styles.itemList}>
                    {o.items.map((i) => (
                      <li key={`${o.id}-${i.variant_sku}`} className={styles.itemRow}>
                        <OpenableProductThumb
                          name={i.name}
                          thumbUrl={i.thumb_url}
                          imageUrl={i.image_url}
                          size="sm"
                        />
                        <span>
                          {i.name} ×{i.quantity} ({i.unit_price} {i.currency})
                        </span>
                      </li>
                    ))}
                  </ul>
                  {Number(o.discount || 0) > 0 ? (
                    <div className="meta">Descuento {o.discount} BOB</div>
                  ) : null}
                </td>
                <td>{o.total ? `${o.total} BOB` : "—"}</td>
                <td>
                  <div className="actions">
                    <Link className={`secondary ${styles.rowAction}`} href={withParams(q, { edit: o.id })}>
                      Editar
                    </Link>
                    {o.payment_status === "confirmed" && !o.has_delivery ? (
                      <Link className={`secondary ${styles.rowAction}`} href={withParams(q, { delivery: o.id })}>
                        Completar entrega
                      </Link>
                    ) : null}
                    {o.payment_status === "confirmed" && o.status !== "delivered" ? (
                      <form action={markDelivered.bind(null, o.id)}>
                        <button type="submit">Entregado</button>
                      </form>
                    ) : null}
                    {o.status !== "cancelled" ? (
                      <form action={setStatus.bind(null, o.id, "cancelled")}>
                        <button className="secondary" type="submit">
                          Cancelar
                        </button>
                      </form>
                    ) : (
                      <form
                        action={setStatus.bind(
                          null,
                          o.id,
                          o.payment_status === "confirmed" ? "placed" : "reserved",
                        )}
                      >
                        <button className="secondary" type="submit">
                          Reabrir
                        </button>
                      </form>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!error && orders.length === 0 ? (
        <p className="meta">{q ? "Ningún pedido coincide con la búsqueda." : "Todavía no hay pedidos."}</p>
      ) : null}
    </>
  );
}
