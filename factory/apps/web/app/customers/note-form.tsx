"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function NoteForm({ customerId }: { customerId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/customers/${customerId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: String(data.get("body") || "").trim() }),
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
      <label className="wide">
        Nota
        <input name="body" placeholder="Prefiere envío por la tarde" required />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? "…" : "Guardar nota"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
