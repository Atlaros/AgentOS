"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function AddProductForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const text = (key: string) => String(data.get(key) || "").trim();
    const codigo = text("codigo");
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/catalog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          codigo,
          codigo_referencia: text("codigo_referencia") || codigo,
          name: text("name"),
          description: text("description"),
          category: text("category") || "general",
          subcategory: text("subcategory"),
          brand: text("brand"),
          material: text("material"),
          season: text("season"),
          style: text("style"),
          talla: text("talla"),
          color: text("color"),
          price: text("price"),
          stock: Number(data.get("stock") || 0),
          image_url: text("image_url"),
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      form.reset();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="product-form" onSubmit={onSubmit}>
      <label>
        Código
        <input name="codigo" placeholder="c055" required />
      </label>
      <label>
        Nombre
        <input name="name" placeholder="Café con leche 200ml" required />
      </label>
      <label>
        Categoría
        <input name="category" placeholder="cafe, empanadas, gaseosas…" />
      </label>
      <label>
        Precio Bs
        <input name="price" inputMode="decimal" required />
      </label>
      <label>
        Stock
        <input name="stock" type="number" min={0} defaultValue={0} />
      </label>
      <details className="wide product-form-more">
        <summary>Más detalles (opcional)</summary>
        <div className="product-form-more-grid">
          <label>
            Código referencia
            <input name="codigo_referencia" placeholder="igual al código si no cambia" />
          </label>
          <label>
            Subcategoría
            <input name="subcategory" placeholder="fritas, 350ml…" />
          </label>
          <label>
            Descripción
            <input name="description" />
          </label>
          <label>
            Imagen (URL)
            <input name="image_url" placeholder="https://…" />
          </label>
          <label>
            Marca
            <input name="brand" />
          </label>
          <label>
            Presentación
            <input name="talla" placeholder="200ml, lata…" />
          </label>
          <label>
            Variante
            <input name="color" placeholder="con leche, con agua…" />
          </label>
          <label>
            Material
            <input name="material" />
          </label>
          <label>
            Temporada
            <input name="season" />
          </label>
          <label>
            Estilo
            <input name="style" />
          </label>
        </div>
      </details>
      <button type="submit" disabled={busy}>
        {busy ? "Guardando…" : "Agregar producto"}
      </button>
      {error ? <p className="error wide">No se pudo guardar ({error}).</p> : null}
    </form>
  );
}
