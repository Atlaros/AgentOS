"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import styles from "./orders.module.css";

export type CatalogOption = {
  variant_sku: string;
  name: string;
  price: string;
  currency: string;
  talla?: string;
  color?: string;
  available?: boolean;
  stock?: number;
};

type DraftLine = {
  variant_sku: string;
  quantity: number;
};

const ERRORS: Record<string, string> = {
  unknown_variant: "Ese producto no está en el catálogo.",
  out_of_stock: "No hay stock, o el producto está reservado en otro pedido.",
  disabled_variant: "Ese producto ya está vendido.",
  bad_wa: "El WhatsApp no es válido.",
  bad_quantity: "La cantidad tiene que ser al menos 1.",
  empty: "Falta el WhatsApp o al menos un producto.",
  bad_amount: "El total del catálogo no se puede cobrar.",
};

function garmentLabel(product: CatalogOption): string {
  const size = [product.talla, product.color].filter(Boolean).join(" ");
  const price = `${product.price} ${product.currency}`;
  return size ? `${product.name} · ${size} · ${price}` : `${product.name} · ${price}`;
}

export function ManualOrderForm({ products }: { products: CatalogOption[] }) {
  const router = useRouter();
  const sellable = useMemo(
    () => products.filter((item) => item.available !== false && (item.stock ?? 1) >= 1),
    [products],
  );
  const [filter, setFilter] = useState("");
  const [sku, setSku] = useState("");
  const [qty, setQty] = useState(1);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const pool = needle
      ? sellable.filter((item) =>
          `${item.name} ${item.variant_sku} ${item.talla || ""} ${item.color || ""}`
            .toLowerCase()
            .includes(needle),
        )
      : sellable;
    return pool.slice(0, 40);
  }, [filter, sellable]);

  function addLine() {
    const variant = sku || shown[0]?.variant_sku || "";
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
    if (lines.length === 0) {
      setError("Agregá al menos un producto.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const recipient = String(data.get("recipient_name") || "").trim();
    const shipTo = String(data.get("delivery_address") || "").trim();
    if ((recipient && !shipTo) || (!recipient && shipTo)) {
      setError("Para la entrega hacen falta quién recibe y la dirección.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          wa_number: String(data.get("wa_number") || "").trim(),
          name: String(data.get("name") || "").trim(),
          address: String(data.get("address") || "").trim(),
          items: lines,
          recipient_name: String(data.get("recipient_name") || "").trim(),
          delivery_address: String(data.get("delivery_address") || "").trim(),
        }),
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: unknown };
          detail = typeof body.detail === "string" ? body.detail : "";
        } catch {
          detail = "";
        }
        setError(ERRORS[detail] || "No se pudo registrar el pedido.");
        return;
      }
      form.reset();
      setLines([]);
      setSku("");
      setQty(1);
      router.refresh();
    } catch {
      setError("No se pudo registrar el pedido.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="orders-manual-title">
      <h2 id="orders-manual-title" className={styles.panelTitle}>
        Nuevo pedido (caja)
      </h2>
      <p className={styles.panelLead}>
        Venta ya cobrada en efectivo. El precio sale del catálogo. No confirma un QR de Baneco.
      </p>
      <form className={styles.panelForm} onSubmit={onSubmit}>
        <label>
          WhatsApp
          <input name="wa_number" required inputMode="tel" autoComplete="tel" placeholder="591…" />
        </label>
        <label>
          Nombre
          <input name="name" autoComplete="name" />
        </label>
        <label>
          Dirección
          <input name="address" autoComplete="street-address" />
        </label>
        <div className={styles.lines}>
          <div className={styles.addRow}>
            <label>
              Prenda
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filtrar catálogo"
                aria-label="Filtrar catálogo"
              />
              <select value={sku} onChange={(event) => setSku(event.target.value)}>
                <option value="">Elegí un producto…</option>
                {shown.map((item) => (
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
          {lines.length === 0 ? (
            <p className="meta">Todavía no agregaste productos.</p>
          ) : (
            <ul className={styles.lineList}>
              {lines.map((line) => {
                const product = sellable.find((item) => item.variant_sku === line.variant_sku);
                return (
                  <li key={line.variant_sku} className={styles.lineRow}>
                    <span>
                      {product ? garmentLabel(product) : line.variant_sku}
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
          )}
        </div>
        <label>
          Quién recibe
          <input name="recipient_name" autoComplete="name" />
        </label>
        <label>
          Dirección de entrega
          <input name="delivery_address" autoComplete="street-address" />
        </label>
        <button type="submit" disabled={busy || lines.length === 0}>
          {busy ? "Registrando…" : "Registrar cobrado"}
        </button>
        {error ? (
          <p className={styles.formError} role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </section>
  );
}
