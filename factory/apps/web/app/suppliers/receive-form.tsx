"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import type { SupplierRow } from "./directory-form";
import styles from "./suppliers.module.css";

type CatalogHit = {
  variant_sku: string;
  name: string;
  codigo?: string;
  stock?: number;
  price?: string | number;
};

type ReceiveFormProps = {
  suppliers: SupplierRow[];
};

export function ReceiveForm({ suppliers }: ReceiveFormProps) {
  const router = useRouter();
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CatalogHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<CatalogHit | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [unitCost, setUnitCost] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<"cash" | "credit">("cash");
  const [receivedAt, setReceivedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (!q || selected) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const handle = window.setTimeout(async () => {
      try {
        const res = await fetch(
          `/api/backend/api/cash/catalog?q=${encodeURIComponent(q)}`,
          { cache: "no-store" },
        );
        if (!res.ok) {
          setHits([]);
          return;
        }
        const body = (await res.json()) as { hits?: CatalogHit[] };
        setHits(Array.isArray(body.hits) ? body.hits : []);
      } catch {
        setHits([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, selected]);

  function pickHit(hit: CatalogHit) {
    setSelected(hit);
    setQuery(hit.name);
    setHits([]);
    setError("");
    setOk("");
  }

  function clearSelection() {
    setSelected(null);
    setQuery("");
    setHits([]);
    setOk("");
    searchRef.current?.focus();
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected?.variant_sku) {
      setError("Elegí un producto del buscador.");
      return;
    }
    const qty = Number(quantity);
    const cost = Number(String(unitCost).replace(",", "."));
    if (!Number.isFinite(qty) || qty < 1) {
      setError("Cantidad inválida.");
      return;
    }
    if (!Number.isFinite(cost) || cost <= 0) {
      setError("El costo unitario es obligatorio y debe ser mayor a 0.");
      return;
    }
    setBusy(true);
    setError("");
    setOk("");
    try {
      const payload: Record<string, string | number> = {
        variant_sku: selected.variant_sku,
        quantity: qty,
        unit_cost: String(cost),
        payment_method: paymentMethod,
      };
      if (supplierId) payload.supplier_id = supplierId;
      if (receivedAt.trim()) {
        const local = new Date(receivedAt.trim());
        if (Number.isNaN(local.getTime())) {
          throw new Error("Fecha inválida");
        }
        payload.received_at = local.toISOString();
      }
      const res = await fetch("/api/backend/api/stock/receive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = String(res.status);
        try {
          const body = (await res.json()) as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      const body = (await res.json()) as { stock?: number; received?: number };
      setOk(
        `Ingresaron ${body.received ?? qty} u. · stock ${body.stock ?? "—"}.`,
      );
      setQuantity("1");
      setUnitCost("");
      setReceivedAt("");
      clearSelection();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  const activeSuppliers = suppliers.filter((item) => item.active !== false);

  return (
    <form className={styles.panel} onSubmit={onSubmit}>
      <h3 className={styles.panelTitle}>Ingreso directo</h3>
      <p className={styles.panelLead}>
        Buscá el producto, cargá cantidad y costo. Contado asienta Inventario/Caja; crédito,
        Inventario/CxP.
      </p>

      <div className={styles.formGrid}>
        <label className={styles.searchField}>
          Producto
          <input
            ref={searchRef}
            value={query}
            onChange={(ev) => {
              setQuery(ev.target.value);
              setSelected(null);
              setOk("");
            }}
            placeholder="Nombre o código"
            autoComplete="off"
            required={!selected}
          />
        </label>
        <label>
          Cantidad
          <input
            type="number"
            min={1}
            step={1}
            value={quantity}
            onChange={(ev) => setQuantity(ev.target.value)}
            required
          />
        </label>
        <label>
          Costo unitario
          <input
            type="number"
            min={0.01}
            step="0.01"
            value={unitCost}
            onChange={(ev) => setUnitCost(ev.target.value)}
            placeholder="Obligatorio"
            required
          />
        </label>
        <label>
          Proveedor
          <select
            value={supplierId}
            onChange={(ev) => setSupplierId(ev.target.value)}
          >
            <option value="">Sin proveedor</option>
            {activeSuppliers.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Forma de pago
          <select
            value={paymentMethod}
            onChange={(ev) =>
              setPaymentMethod(ev.target.value === "credit" ? "credit" : "cash")
            }
          >
            <option value="cash">Contado</option>
            <option value="credit">Crédito</option>
          </select>
        </label>
        <label>
          Fecha (opcional)
          <input
            type="datetime-local"
            value={receivedAt}
            onChange={(ev) => setReceivedAt(ev.target.value)}
          />
        </label>
      </div>

      {selected ? (
        <p className={styles.selectedProduct}>
          Seleccionado: <strong>{selected.name}</strong> ·{" "}
          <code>{selected.variant_sku}</code>
          {selected.codigo ? ` · ${selected.codigo}` : ""}
          <button type="button" className={styles.clearPick} onClick={clearSelection}>
            Cambiar
          </button>
        </p>
      ) : null}

      {!selected && searching ? <p className="meta">Buscando…</p> : null}
      {!selected && hits.length > 0 ? (
        <ul className={styles.searchHits}>
          {hits.map((hit) => (
            <li key={hit.variant_sku} className={styles.searchHit}>
              <button
                type="button"
                className={styles.searchHitButton}
                onClick={() => pickHit(hit)}
              >
                <span className={styles.searchHitMeta}>
                  <span className={styles.searchHitName}>{hit.name}</span>
                  <span className={styles.searchHitDetail}>
                    <code>{hit.variant_sku}</code>
                    {hit.codigo ? ` · ${hit.codigo}` : ""}
                    {typeof hit.stock === "number" ? ` · stock ${hit.stock}` : ""}
                  </span>
                </span>
                <span className={styles.searchHitAdd}>Elegir</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className={styles.formActions}>
        <button type="submit" disabled={busy || !selected}>
          {busy ? "…" : "Ingresar stock"}
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {ok ? <p className="meta">{ok}</p> : null}
    </form>
  );
}
