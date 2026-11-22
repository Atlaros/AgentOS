"use client";

import { useState } from "react";

type BusinessOption = {
  tenant_id: string;
  name: string;
};

type AutonomyPanelProps = {
  businesses: BusinessOption[];
};

export function AutonomyPanel({ businesses }: AutonomyPanelProps) {
  const [tenantId, setTenantId] = useState(businesses[0]?.tenant_id || "");
  const [action, setAction] = useState("adjust_stock");
  const [level, setLevel] = useState("never");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (businesses.length === 0) {
    return null;
  }

  async function tighten() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/backend/api/operator/autonomy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, action, level }),
        cache: "no-store",
      });
      const body = (await response.json()) as {
        detail?: string;
        autonomy?: { action: string; level: string }[];
      };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo apretar la autonomía.");
      }
      const grant = body.autonomy?.find((item) => item.action === action);
      setMessage(
        grant
          ? `Actualizado: ${grant.action} → ${grant.level}. Actualizá la página para ver la tabla.`
          : "Actualizado. Actualizá la página para ver la tabla.",
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo apretar la autonomía.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="operator-autonomy-title">
      <h2 id="operator-autonomy-title" className="sr-only">
        Apretar autonomía
      </h2>
      <div className="login-form">
        <label htmlFor="autonomy-business">Negocio</label>
        <select
          id="autonomy-business"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
        >
          {businesses.map((row) => (
            <option key={row.tenant_id} value={row.tenant_id}>
              {row.name}
            </option>
          ))}
        </select>
        <label htmlFor="autonomy-action">Acción</label>
        <select
          id="autonomy-action"
          value={action}
          onChange={(event) => setAction(event.target.value)}
        >
          <option value="adjust_stock">Ajuste de stock</option>
          <option value="post_journal">Asiento contable</option>
          <option value="reply_customer">Respuesta al cliente</option>
          <option value="confirm_payment">Confirmar un pago</option>
        </select>
        <label htmlFor="autonomy-level">Nivel</label>
        <select
          id="autonomy-level"
          value={level}
          onChange={(event) => setLevel(event.target.value)}
        >
          <option value="never">Nunca</option>
          <option value="recommend">Solo recomendar</option>
          <option value="approval">Con aprobación</option>
          <option value="within_limits">Dentro de límites</option>
        </select>
        <button type="button" disabled={busy || !tenantId} onClick={tighten}>
          {busy ? "Guardando…" : "Apretar"}
        </button>
      </div>
      {message ? <p className="meta">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
