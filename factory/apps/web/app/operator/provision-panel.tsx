"use client";

import { useState } from "react";

type ProvisionPanelProps = {
  onCreated?: () => void;
};

export function ProvisionPanel({ onCreated }: ProvisionPanelProps) {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("cafe");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function provision(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/backend/api/operator/businesses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, industry }),
        cache: "no-store",
      });
      const body = (await response.json()) as {
        detail?: string;
        name?: string;
        tenant_id?: string;
      };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo crear el negocio.");
      }
      setMessage(
        body.name
          ? `Se creó ${body.name}. Actualizá la página para verlo en la lista.`
          : "Listo. Actualizá la página para verlo en la lista.",
      );
      setName("");
      onCreated?.();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo crear el negocio.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="operator-provision-title">
      <h2 id="operator-provision-title">Dar de alta un negocio</h2>
      <p className="meta">
        Crea un tenant de cafetería o ropa desde la plantilla. No abre el alta pública.
      </p>
      <form className="login-form" onSubmit={provision}>
        <label htmlFor="provision-name">Nombre</label>
        <input
          id="provision-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <label htmlFor="provision-industry">Rubro</label>
        <select
          id="provision-industry"
          value={industry}
          onChange={(event) => setIndustry(event.target.value)}
        >
          <option value="cafe">Cafetería</option>
          <option value="ropa">Ropa</option>
        </select>
        <button type="submit" disabled={busy}>
          {busy ? "Creando…" : "Crear negocio"}
        </button>
      </form>
      {message ? <p className="meta">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
