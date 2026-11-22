"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function ResetSecretForm({ userId, userName }: { userId: string; userName: string }) {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setOk("");
    try {
      const response = await fetch(`/api/backend/api/panel/users/${userId}/secret`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret }),
      });
      if (!response.ok) {
        setError("No se pudo restablecer la clave.");
        return;
      }
      setSecret("");
      setOpen(false);
      setOk(`Clave nueva para ${userName}.`);
      router.refresh();
    } catch {
      setError("No se pudo restablecer la clave.");
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <div>
        <button type="button" className="secondary" onClick={() => setOpen(true)}>
          Restablecer clave
        </button>
        {ok ? <p className="lead">{ok}</p> : null}
      </div>
    );
  }

  return (
    <form onSubmit={submit}>
      <label htmlFor={`reset-secret-${userId}`}>Nueva clave</label>
      <input
        id={`reset-secret-${userId}`}
        type="password"
        value={secret}
        onChange={(event) => setSecret(event.target.value)}
        minLength={8}
        required
        autoComplete="new-password"
      />
      <button type="submit" disabled={pending}>
        {pending ? "Guardando…" : "Guardar clave"}
      </button>
      <button type="button" className="secondary" disabled={pending} onClick={() => setOpen(false)}>
        Cancelar
      </button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
