"use client";

import { useState } from "react";
import Link from "next/link";

type Created = {
  name: string;
  owner_email: string;
  owner_secret: string;
};

export function SignupForm() {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("cafe");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<Created | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/public/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, industry, invite }),
      });
      const body = (await response.json()) as {
        error?: string;
        name?: string;
        owner_email?: string;
        owner_secret?: string;
      };
      if (!response.ok) {
        if (body.error === "signup_disabled") {
          throw new Error("El alta pública está apagada.");
        }
        if (body.error === "invite_required") {
          throw new Error("Necesitás una invitación vigente.");
        }
        if (body.error === "signup_rate_limited") {
          throw new Error("Demasiados altas desde esta red. Probá más tarde.");
        }
        throw new Error("No se pudo crear el negocio.");
      }
      if (!body.owner_email || !body.owner_secret || !body.name) {
        throw new Error("No se pudo crear el negocio.");
      }
      setCreated({
        name: body.name,
        owner_email: body.owner_email,
        owner_secret: body.owner_secret,
      });
      setInvite("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo crear el negocio.");
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div>
        <p>
          Listo: <strong>{created.name}</strong>. Guardá este correo y esta clave; la clave no se
          vuelve a mostrar.
        </p>
        <p>
          Correo: <code>{created.owner_email}</code>
        </p>
        <p>
          Clave: <code>{created.owner_secret}</code>
        </p>
        <p>
          <Link href="/owner">Entrar a tu negocio</Link>
        </p>
      </div>
    );
  }

  return (
    <form className="login-form" onSubmit={submit}>
      <label htmlFor="signup-name">Nombre del negocio</label>
      <input
        id="signup-name"
        autoComplete="organization"
        value={name}
        onChange={(event) => setName(event.target.value)}
        required
      />
      <label htmlFor="signup-industry">Rubro</label>
      <select
        id="signup-industry"
        value={industry}
        onChange={(event) => setIndustry(event.target.value)}
      >
        <option value="cafe">Cafetería</option>
        <option value="ropa">Ropa</option>
      </select>
      <label htmlFor="signup-invite">Invitación</label>
      <input
        id="signup-invite"
        autoComplete="off"
        value={invite}
        onChange={(event) => setInvite(event.target.value)}
        required
      />
      <button type="submit" disabled={busy}>
        {busy ? "Creando…" : "Crear negocio"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
