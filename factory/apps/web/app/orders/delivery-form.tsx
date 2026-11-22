"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import styles from "./orders.module.css";

const ERRORS: Record<string, string> = {
  empty: "Nombre y dirección son obligatorios.",
  delivery_exists: "Esta entrega ya está registrada.",
  payment_not_confirmed: "El pago no está confirmado. No se registra la entrega.",
};

export type DeliveryCandidate = {
  id: string;
  label: string;
  location: string;
};

export function DeliveryForm({
  candidates,
  initialOrderId = "",
}: {
  candidates: DeliveryCandidate[];
  initialOrderId?: string;
}) {
  const router = useRouter();
  const [orderId, setOrderId] = useState(initialOrderId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialOrderId) setOrderId(initialOrderId);
  }, [initialOrderId]);

  if (candidates.length === 0) {
    return (
      <section className={styles.panel} aria-labelledby="orders-delivery-title">
        <h2 id="orders-delivery-title" className={styles.panelTitle}>
          Registrar entrega
        </h2>
        <p className="meta">
          No hay pedidos con pago confirmado pendientes de entrega. Este formulario no confirma el
          pago.
        </p>
      </section>
    );
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!orderId) {
      setError("Elegí un pedido.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/orders/${orderId}/delivery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient_name: String(data.get("recipient_name") || "").trim(),
          address: String(data.get("address") || "").trim(),
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
        setError(ERRORS[detail] || "No se pudo registrar la entrega.");
        return;
      }
      form.reset();
      setOrderId("");
      router.replace("/orders");
      router.refresh();
    } catch {
      setError("No se pudo registrar la entrega.");
    } finally {
      setBusy(false);
    }
  }

  const selected = candidates.find((row) => row.id === orderId);

  return (
    <section className={styles.panel} aria-labelledby="orders-delivery-title">
      <h2 id="orders-delivery-title" className={styles.panelTitle}>
        Registrar entrega
      </h2>
      <p className="meta">
        Si el agente no cargó la entrega, completála acá. No confirma el pago: solo escribe con pago
        ya confirmado.
      </p>
      <form className={styles.panelForm} onSubmit={onSubmit}>
        <label>
          Pedido
          <select
            value={orderId}
            onChange={(event) => setOrderId(event.target.value)}
            required
          >
            <option value="">Pedido ya cobrado…</option>
            {candidates.map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Quién recibe
          <input name="recipient_name" required autoComplete="name" />
        </label>
        <label>
          Dirección
          <input
            name="address"
            required
            autoComplete="street-address"
            defaultValue={selected?.location || ""}
            key={orderId || "empty"}
          />
        </label>
        <button type="submit" disabled={busy || !orderId}>
          {busy ? "Registrando…" : "Registrar entrega"}
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
