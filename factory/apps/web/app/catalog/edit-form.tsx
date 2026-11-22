"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./catalog.module.css";

export type EditableProduct = {
  variant_sku: string;
  codigo: string;
  name: string;
  description?: string;
  category: string;
  subcategory?: string;
  brand?: string;
  material?: string;
  talla?: string;
  color?: string;
  price: string;
  currency: string;
  stock: number;
};

const ERRORS: Record<string, string> = {
  bad_stock: "El stock no puede ser negativo.",
  bad_price: "El precio no es válido.",
  bad_name: "El nombre no puede quedar vacío.",
  variant_not_found: "Ese producto no está en el inventario.",
};

export function EditProductForm({
  product,
  closeHref,
}: {
  product: EditableProduct;
  closeHref: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const text = (key: string) => String(data.get(key) || "").trim();
    const stock = Number(data.get("stock"));
    if (!text("name")) {
      setError(ERRORS.bad_name);
      return;
    }
    if (!text("price") || Number.isNaN(Number(text("price").replace(",", ".")))) {
      setError(ERRORS.bad_price);
      return;
    }
    if (!Number.isInteger(stock) || stock < 0) {
      setError(ERRORS.bad_stock);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/catalog/${encodeURIComponent(product.variant_sku)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: text("name"),
          price: text("price"),
          stock,
          category: text("category"),
          subcategory: text("subcategory"),
          talla: text("talla"),
          color: text("color"),
          material: text("material"),
          brand: text("brand"),
          description: text("description"),
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
        setError(ERRORS[detail] || "No se pudo guardar el producto.");
        return;
      }
      router.replace(closeHref);
      router.refresh();
    } catch {
      setError("No se pudo guardar el producto.");
    } finally {
      setBusy(false);
    }
  }

  const code = product.codigo || product.variant_sku;

  return (
    <section className={styles.panel} aria-labelledby="catalog-edit-title">
      <div className={styles.panelHead}>
        <h2 id="catalog-edit-title" className={styles.panelTitle}>
          Editar {code}
        </h2>
        <a className={styles.clear} href={closeHref}>
          Cerrar
        </a>
      </div>
      <p className={styles.panelLead}>
        {product.name} · {product.price} {product.currency}. El código no se cambia. Para el stock
        del día también podés editarlo directo en la tabla.
      </p>
      <form className={styles.panelForm} onSubmit={onSubmit}>
        <label>
          Nombre
          <input name="name" defaultValue={product.name} required />
        </label>
        <label>
          Precio Bs
          <input name="price" defaultValue={product.price} inputMode="decimal" required />
        </label>
        <label>
          Stock
          <input name="stock" type="number" min={0} step={1} defaultValue={product.stock} required />
        </label>
        <label>
          Categoría
          <input name="category" defaultValue={product.category} />
        </label>
        <details className={styles.wide}>
          <summary>Más detalles (opcional)</summary>
          <div className={styles.moreGrid}>
            <label>
              Subcategoría
              <input name="subcategory" defaultValue={product.subcategory || ""} />
            </label>
            <label>
              Presentación
              <input name="talla" defaultValue={product.talla || ""} placeholder="200ml, lata…" />
            </label>
            <label>
              Variante
              <input name="color" defaultValue={product.color || ""} placeholder="con leche…" />
            </label>
            <label>
              Material
              <input name="material" defaultValue={product.material || ""} />
            </label>
            <label>
              Marca
              <input name="brand" defaultValue={product.brand || ""} />
            </label>
            <label className={styles.wide}>
              Descripción
              <textarea name="description" defaultValue={product.description || ""} rows={3} />
            </label>
          </div>
        </details>
        <button type="submit" disabled={busy}>
          {busy ? "Guardando…" : "Guardar producto"}
        </button>
        {error ? <p className={styles.formError}>{error}</p> : null}
      </form>
    </section>
  );
}
