"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { OpenableProductThumb } from "@/components/openable-product-thumb";

import { supplierHref } from "./suppliers-tabs";
import styles from "./suppliers.module.css";

export type ReplenishmentItem = {
  variant_sku: string;
  name: string;
  codigo?: string;
  stock: number;
  reorder_threshold: number;
  sold_proxy?: number;
  ventas?: number;
  suggested_qty: number;
  supplier_id?: string | null;
  media_id?: string;
  thumb_url?: string;
  image_url?: string;
};

export type ReplenishmentGroup = {
  supplier_id: string | null;
  supplier_name: string;
  items: ReplenishmentItem[];
};

export type ReplenishmentPayload = {
  cards: {
    sin_stock: number;
    stock_bajo: number;
    ordenes_en_camino: number;
  };
  groups: ReplenishmentGroup[];
  heuristic_note?: string;
};

type SelectionState = Record<
  string,
  { checked: boolean; qty: number }
>;

function itemKey(supplierKey: string, sku: string): string {
  return `${supplierKey}::${sku}`;
}

export function ReplenishmentPanel({ data }: { data: ReplenishmentPayload }) {
  const router = useRouter();
  const [selection, setSelection] = useState<SelectionState>(() => {
    const initial: SelectionState = {};
    for (const group of data.groups) {
      const gKey = group.supplier_id || "none";
      for (const item of group.items) {
        initial[itemKey(gKey, item.variant_sku)] = {
          checked: false,
          qty: Math.max(1, Number(item.suggested_qty) || 1),
        };
      }
    }
    return initial;
  });
  const [busyGroup, setBusyGroup] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const cards = data.cards;

  const totals = useMemo(() => {
    let selected = 0;
    for (const value of Object.values(selection)) {
      if (value.checked) selected += 1;
    }
    return selected;
  }, [selection]);

  function toggleItem(key: string, checked: boolean) {
    setSelection((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { qty: 1, checked: false }), checked },
    }));
    setError("");
    setOk("");
  }

  function setQty(key: string, qtyRaw: string) {
    const qty = Math.max(1, Math.floor(Number(qtyRaw) || 1));
    setSelection((prev) => ({
      ...prev,
      [key]: { ...(prev[key] || { checked: true, qty }), qty, checked: prev[key]?.checked ?? true },
    }));
  }

  async function generateOrder(group: ReplenishmentGroup) {
    if (!group.supplier_id) {
      setError("Asigná un proveedor en Directorio antes de generar el pedido.");
      return;
    }
    const gKey = group.supplier_id;
    const lines = group.items
      .map((item) => {
        const key = itemKey(gKey, item.variant_sku);
        const state = selection[key];
        if (!state?.checked) return null;
        return {
          variant_sku: item.variant_sku,
          quantity: Math.max(1, Number(state.qty) || 1),
        };
      })
      .filter(Boolean) as Array<{ variant_sku: string; quantity: number }>;

    if (lines.length === 0) {
      setError("Marcá al menos un producto del grupo para generar el pedido.");
      return;
    }

    setBusyGroup(gKey);
    setError("");
    setOk("");
    try {
      const res = await fetch("/api/backend/api/purchase-orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supplier_id: group.supplier_id,
          lines,
        }),
      });
      const body = (await res.json().catch(() => ({}))) as {
        id?: string;
        number?: string;
        detail?: string;
      };
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : "No se pudo crear el pedido.");
        return;
      }
      setOk(
        `Pedido ${body.number || body.id || ""} creado en borrador. Ver en Órdenes.`,
      );
      setSelection((prev) => {
        const next = { ...prev };
        for (const item of group.items) {
          const key = itemKey(gKey, item.variant_sku);
          if (next[key]) next[key] = { ...next[key], checked: false };
        }
        return next;
      });
      router.refresh();
    } catch {
      setError("Error de red al crear el pedido.");
    } finally {
      setBusyGroup(null);
    }
  }

  return (
    <div className={styles.replenishWrap}>
      <div className={styles.cardRow} aria-label="Resumen de reposición">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Sin stock</span>
          <strong className={styles.statValue}>{cards.sin_stock}</strong>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Stock bajo</span>
          <strong className={styles.statValue}>{cards.stock_bajo}</strong>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Órdenes en camino</span>
          <strong className={styles.statValue}>{cards.ordenes_en_camino}</strong>
        </div>
      </div>

      <p className={styles.panelLead}>
        Cantidad sugerida editable (heurística simple: déficit + 1 + ventas proxy
        capadas). No es un EOQ óptimo. Seleccionadas: {totals}.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {ok ? (
        <p className={styles.okBanner}>
          {ok}{" "}
          <Link href={supplierHref("ordenes")} className={styles.inlineLink}>
            Ir a Órdenes
          </Link>
        </p>
      ) : null}

      {data.groups.length === 0 ? (
        <p className={styles.muted}>Nada por reponer según umbral.</p>
      ) : (
        data.groups.map((group) => {
          const gKey = group.supplier_id || "none";
          const canOrder = Boolean(group.supplier_id);
          return (
            <section key={gKey} className={styles.panel}>
              <div className={styles.groupHeader}>
                <h3 className={styles.panelTitle}>{group.supplier_name}</h3>
                {canOrder ? (
                  <button
                    type="button"
                    className={styles.primaryBtn}
                    disabled={busyGroup === group.supplier_id}
                    onClick={() => void generateOrder(group)}
                  >
                    {busyGroup === group.supplier_id ? "Generando…" : "Generar pedido"}
                  </button>
                ) : (
                  <p className={styles.assignHint}>
                    Sin proveedor: asigná en{" "}
                    <Link href={supplierHref("directorio")}>Directorio</Link> para
                    poder generar OC.
                  </p>
                )}
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th aria-label="Seleccionar" />
                      <th aria-label="Foto" />
                      <th>Código</th>
                      <th>Nombre</th>
                      <th>Stock</th>
                      <th>Umbral</th>
                      <th>Ventas</th>
                      <th>Sugerido</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((item) => {
                      const key = itemKey(gKey, item.variant_sku);
                      const state = selection[key] || {
                        checked: false,
                        qty: item.suggested_qty,
                      };
                      return (
                        <tr key={item.variant_sku}>
                          <td>
                            <input
                              type="checkbox"
                              checked={state.checked}
                              disabled={!canOrder}
                              onChange={(e) => toggleItem(key, e.target.checked)}
                              aria-label={`Seleccionar ${item.name}`}
                            />
                          </td>
                          <td>
                            <OpenableProductThumb
                              name={item.name}
                              thumbUrl={item.thumb_url}
                              imageUrl={item.image_url}
                              size="sm"
                            />
                          </td>
                          <td>{item.codigo || "—"}</td>
                          <td>
                            {item.name}
                            <div className={styles.muted}>
                              <code>{item.variant_sku}</code>
                            </div>
                          </td>
                          <td>{item.stock}</td>
                          <td>{item.reorder_threshold}</td>
                          <td>{item.ventas ?? item.sold_proxy ?? 0}</td>
                          <td>
                            <input
                              className={styles.qtyInput}
                              type="number"
                              min={1}
                              disabled={!canOrder}
                              value={state.qty}
                              onChange={(e) => setQty(key, e.target.value)}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
