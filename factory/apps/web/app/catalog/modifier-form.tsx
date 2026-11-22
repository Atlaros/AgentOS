"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ERRORS: Record<string, string> = {
  panel_forbidden: "Sin permiso para crear un extra.",
  bad_name: "El nombre del extra no es válido.",
  bad_price: "La diferencia de precio no es válida.",
};

export function ModifierForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const name = String(data.get("name") || "").trim();
    const price = String(data.get("price_delta") || "").trim();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/catalog/modifiers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, price_delta: price }),
      });
      if (!res.ok) {
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: string };
          detail = String(body.detail || "");
        } catch {
          detail = "";
        }
        setError(ERRORS[detail] || "No se pudo guardar el extra.");
        return;
      }
      form.reset();
      router.refresh();
    } catch {
      setError("No se pudo guardar el extra.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="product-form" onSubmit={onSubmit}>
      <h2>Extra</h2>
      <p className="meta">
        Nombre y diferencia de precio. El cajero lo elige en el ticket. El stock sigue la variante.
      </p>
      <label>
        Nombre
        <input name="name" required />
      </label>
      <label>
        Diferencia Bs
        <input name="price_delta" placeholder="3.50" required />
      </label>
      <button type="submit" disabled={busy}>
        Guardar extra
      </button>
      {error ? <p className="error wide">{error}</p> : null}
    </form>
  );
}
