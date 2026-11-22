"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ERRORS: Record<string, string> = {
  pin_required: "El PIN es obligatorio.",
  bad_pin: "PIN incorrecto.",
  pin_locked: "PIN bloqueado por intentos fallidos.",
  panel_forbidden: "Sin permiso para crear un combo.",
  bad_combo: "El combo necesita componentes que existan y no sean otros combos.",
  unknown_variant: "Uno de los componentes no está en el catálogo.",
  bad_price: "El precio no es válido.",
  bad_date: "La fecha del evento no es válida.",
  combo_exists: "Ya existe un producto con ese código.",
  codigo_and_name_required: "El código y el nombre son obligatorios.",
};

function parseComponents(raw: string): { variant_sku: string; quantity: number }[] {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.map((line) => {
    const [sku, qty] = line.split(/\s+/, 2);
    const quantity = Number(qty || "1");
    return { variant_sku: sku, quantity: Number.isFinite(quantity) ? quantity : 0 };
  });
}

export function ComboForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const text = (key: string) => String(data.get(key) || "").trim();
    const components = parseComponents(text("components"));
    if (components.length === 0 || components.some((item) => !item.variant_sku || item.quantity < 1)) {
      setError(ERRORS.bad_combo);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/catalog/combos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          codigo: text("codigo"),
          name: text("name"),
          price: text("price"),
          category: text("category") || "Combos",
          event_date: text("event_date"),
          pin: text("pin"),
          components,
        }),
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: string };
          detail = String(body.detail || "");
        } catch {
          detail = "";
        }
        setError(ERRORS[detail] || "No se pudo guardar el combo.");
        return;
      }
      form.reset();
      router.refresh();
    } catch {
      setError("No se pudo guardar el combo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="product-form" onSubmit={onSubmit}>
      <h2>Combo</h2>
      <p className="meta">
        No tiene stock propio. Vender uno resta cada componente. El precio se fija acá, con PIN.
      </p>
      <label>
        Código
        <input name="codigo" placeholder="desayuno" required />
      </label>
      <label>
        Nombre
        <input name="name" required />
      </label>
      <label>
        Categoría
        <input name="category" placeholder="Combos" />
      </label>
      <label>
        Precio Bs
        <input name="price" required />
      </label>
      <label>
        Fecha del evento
        <input name="event_date" placeholder="2026-12-24" />
      </label>
      <label className="wide">
        Componentes
        <textarea name="components" rows={3} placeholder={"cafe 1\npan 1"} required />
      </label>
      <label>
        PIN
        <input name="pin" type="password" autoComplete="off" />
      </label>
      <button type="submit" disabled={busy}>
        Guardar combo
      </button>
      {error ? <p className="error wide">{error}</p> : null}
    </form>
  );
}
