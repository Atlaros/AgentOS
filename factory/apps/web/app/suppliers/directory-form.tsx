"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./suppliers.module.css";

export type SupplierRow = {
  id: string;
  name: string;
  contact_name: string;
  phone: string;
  whatsapp: string;
  email: string;
  notes: string;
  payment_terms: string;
  lead_time_days: number;
  active: boolean;
};

const EMPTY: Omit<SupplierRow, "id" | "active"> = {
  name: "",
  contact_name: "",
  phone: "",
  whatsapp: "",
  email: "",
  notes: "",
  payment_terms: "cash",
  lead_time_days: 0,
};

export function DirectoryForm({
  initial,
  onDone,
}: {
  initial?: SupplierRow | null;
  onDone?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editing = Boolean(initial?.id);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      name: String(data.get("name") || "").trim(),
      contact_name: String(data.get("contact_name") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      whatsapp: String(data.get("whatsapp") || "").trim(),
      email: String(data.get("email") || "").trim(),
      notes: String(data.get("notes") || "").trim(),
      payment_terms: String(data.get("payment_terms") || "cash").trim() || "cash",
      lead_time_days: Number(data.get("lead_time_days") || 0),
    };
    if (!payload.name) {
      setError("El nombre es obligatorio.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(
        editing
          ? `/api/backend/api/suppliers/${encodeURIComponent(initial!.id)}`
          : "/api/backend/api/suppliers",
        {
          method: editing ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!res.ok) throw new Error(String(res.status));
      event.currentTarget.reset();
      onDone?.();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  const values = initial || EMPTY;

  return (
    <form className={styles.panel} onSubmit={onSubmit}>
      <h3 className={styles.panelTitle}>{editing ? "Editar proveedor" : "Nuevo proveedor"}</h3>
      <p className={styles.panelLead}>
        Datos del directorio. La desactivación es suave: el historial se conserva.
      </p>
      <div className={styles.formGrid}>
        <label>
          Nombre
          <input name="name" defaultValue={values.name} required />
        </label>
        <label>
          Contacto
          <input name="contact_name" defaultValue={values.contact_name} />
        </label>
        <label>
          Teléfono
          <input name="phone" defaultValue={values.phone} />
        </label>
        <label>
          WhatsApp
          <input name="whatsapp" defaultValue={values.whatsapp} />
        </label>
        <label>
          Email
          <input name="email" type="email" defaultValue={values.email} />
        </label>
        <label>
          Condición de pago
          <select name="payment_terms" defaultValue={values.payment_terms || "cash"}>
            <option value="cash">Contado</option>
            <option value="credit">Crédito</option>
          </select>
        </label>
        <label>
          Plazo (días)
          <input
            name="lead_time_days"
            type="number"
            min={0}
            defaultValue={values.lead_time_days}
          />
        </label>
        <label>
          Notas
          <input name="notes" defaultValue={values.notes} />
        </label>
      </div>
      <div className={styles.formActions}>
        <button type="submit" disabled={busy}>
          {busy ? "…" : editing ? "Guardar" : "Crear proveedor"}
        </button>
        {editing ? (
          <button type="button" onClick={() => onDone?.()} disabled={busy}>
            Cancelar
          </button>
        ) : null}
      </div>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
