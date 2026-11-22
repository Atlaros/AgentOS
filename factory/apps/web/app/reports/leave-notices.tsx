"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function LeaveNotices() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function leave() {
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/backend/api/reminders/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ send: false }),
      });
      if (!response.ok) {
        setError("No se pudieron dejar los avisos.");
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudieron dejar los avisos.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void leave();
      }}
    >
      <button type="submit" disabled={pending}>
        {pending ? "Dejando avisos…" : "Dejar avisos"}
      </button>
      <p className="lead">El aviso queda en el archivo. Este botón no le escribe al cliente.</p>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
