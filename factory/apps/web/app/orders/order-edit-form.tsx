"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import type { CatalogOption } from "./manual-order-form";
import { OrderAttachments } from "./order-attachments";
import styles from "./orders.module.css";

export type EditableOrder = {
  id: string;
  public_number: string | null;
  customer_name: string | null;
  customer_address?: string | null;
  wa_number: string;
  payment_status: string | null;
  has_delivery?: boolean;
  delivery?: { address: string; recipient_name: string } | null;
  items: {
    variant_sku: string;
    name: string;
    quantity: number;
    unit_price: string;
    currency: string;
  }[];
};

type DraftLine = { variant_sku: string; quantity: number };

const ERRORS: Record<string, string> = {
  unknown_variant: "Ese producto no está en el catálogo.",
  out_of_stock: "No hay stock, o el producto está reservado en otro pedido.",
  disabled_variant: "Ese producto ya está vendido.",
  payment_locked: "El pago ya está confirmado. Los productos no se cambian.",
  empty: "Para la entrega hacen falta nombre y dirección.",
  bad_quantity: "La cantidad tiene que ser al menos 1.",
  order_not_found: "Ese pedido no está.",
};

function garmentLabel(product: CatalogOption): string {
  const size = [product.talla, product.color].filter(Boolean).join(" ");
  const price = `${product.price} ${product.currency}`;
  return size ? `${product.name} · ${size} · ${price}` : `${product.name} · ${price}`;
}

export function OrderEditForm({
  order,
  products,
  closeHref,
}: {
  order: EditableOrder;
  products: CatalogOption[];
  closeHref: string;
}) {
  const router = useRouter();
  const paid = order.payment_status === "confirmed";
  const sellable = useMemo(
    () => products.filter((item) => item.available !== false && (item.stock ?? 1) >= 1),
    [products],
  );
  const [lines, setLines] = useState<DraftLine[]>(
    order.items.map((item) => ({ variant_sku: item.variant_sku, quantity: item.quantity })),
  );
  const [sku, setSku] = useState("");
  const [qty, setQty] = useState(1);
  const [cash, setCash] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function addLine() {
    const variant = sku || sellable[0]?.variant_sku || "";
    if (!variant || qty < 1) {
      setError("Elegí un producto y una cantidad.");
      return;
    }
    setError("");
    setLines((current) => {
      const existing = current.find((line) => line.variant_sku === variant);
      if (existing) {
        return current.map((line) =>
          line.variant_sku === variant ? { ...line, quantity: line.quantity + qty } : line,
        );
      }
      return [...current, { variant_sku: variant, quantity: qty }];
    });
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!paid && lines.length === 0) {
      setError("El pedido necesita al menos un producto.");
      return;
    }
    const data = new FormData(event.currentTarget);
    const recipient = String(data.get("recipient_name") || "").trim();
    const shipTo = String(data.get("delivery_address") || "").trim();
    const payload: Record<string, unknown> = {
      name: String(data.get("name") || "").trim(),
      address: String(data.get("address") || "").trim(),
    };
    if (recipient || shipTo) {
      payload.recipient_name = recipient;
      payload.delivery_address = shipTo;
    }
    if (!paid) {
      payload.items = lines;
      payload.mark_cash_paid = cash;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/orders/${order.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: unknown };
          detail = typeof body.detail === "string" ? body.detail : "";
        } catch {
          detail = "";
        }
        setError(ERRORS[detail] || "No se pudo guardar el pedido.");
        return;
      }
      router.replace(closeHref);
      router.refresh();
    } catch {
      setError("No se pudo guardar el pedido.");
    } finally {
      setBusy(false);
    }
  }

  const number = order.public_number || order.id.slice(0, 8);

  return (
    <section className={styles.panel} aria-labelledby="orders-edit-title">
      <div className={styles.panelHead}>
        <h2 id="orders-edit-title" className={styles.panelTitle}>
          Editar {number}
        </h2>
        <a className={styles.clear} href={closeHref}>
          Cerrar
        </a>
      </div>
      <p className={styles.panelLead}>
        {order.customer_name || "Sin nombre"} · {order.wa_number || "sin WhatsApp"}
        {paid ? " · pago confirmado: los productos quedan como están." : " · sin pago confirmado."}
      </p>
      <form className={styles.panelForm} onSubmit={onSubmit}>
        <label>
          Nombre
          <input name="name" defaultValue={order.customer_name || ""} autoComplete="name" />
        </label>
        <label>
          Dirección
          <input name="address" defaultValue={order.customer_address || ""} autoComplete="street-address" />
        </label>
        {paid ? (
          <div className={styles.lines}>
            <p className="meta">
              {order.items
                .map((item) => `${item.name} ×${item.quantity} (${item.unit_price} ${item.currency})`)
                .join("; ")}
            </p>
          </div>
        ) : (
          <div className={styles.lines}>
            <div className={styles.addRow}>
              <label>
                Prenda
                <select value={sku} onChange={(event) => setSku(event.target.value)}>
                  <option value="">Elegí un producto…</option>
                  {sellable.slice(0, 80).map((item) => (
                    <option key={item.variant_sku} value={item.variant_sku}>
                      {garmentLabel(item)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Cantidad
                <input
                  type="number"
                  min={1}
                  value={qty}
                  onChange={(event) => setQty(Math.max(1, Number(event.target.value) || 1))}
                />
              </label>
              <button type="button" className="secondary" onClick={addLine}>
                Agregar
              </button>
            </div>
            <ul className={styles.lineList}>
              {lines.map((line) => {
                const product = products.find((item) => item.variant_sku === line.variant_sku);
                const known = order.items.find((item) => item.variant_sku === line.variant_sku);
                const label = product
                  ? garmentLabel(product)
                  : known
                    ? `${known.name} · ${known.unit_price} ${known.currency}`
                    : line.variant_sku;
                return (
                  <li key={line.variant_sku} className={styles.lineRow}>
                    <span>
                      {label}
                      <span className={styles.lineMeta}> ×{line.quantity}</span>
                    </span>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        setLines((current) => current.filter((item) => item.variant_sku !== line.variant_sku))
                      }
                    >
                      Quitar
                    </button>
                  </li>
                );
              })}
            </ul>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={cash}
                onChange={(event) => setCash(event.target.checked)}
              />
              Marcar cobrado en caja
            </label>
          </div>
        )}
        <label>
          Quién recibe
          <input
            name="recipient_name"
            defaultValue={order.delivery?.recipient_name || ""}
            autoComplete="name"
          />
        </label>
        <label>
          Dirección de entrega
          <input
            name="delivery_address"
            defaultValue={order.delivery?.address || ""}
            autoComplete="street-address"
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Guardando…" : "Guardar"}
        </button>
        {error ? (
          <p className={styles.formError} role="alert">
            {error}
          </p>
        ) : null}
      </form>
      <OrderAttachments
        orderId={order.id}
        apiPath={`/api/orders/${encodeURIComponent(order.id)}/attachments`}
        title="Adjuntos del pedido"
      />
    </section>
  );
}
