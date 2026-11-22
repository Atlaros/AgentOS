"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function AvailabilityButton({
  variantSku,
  available,
}: {
  variantSku: string;
  available: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function toggle() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch(
        `/api/backend/api/catalog/${encodeURIComponent(variantSku)}/availability`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ available: !available }),
        },
      );
      if (!res.ok) throw new Error(String(res.status));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="avail-cell">
      <button type="button" className="secondary" disabled={busy} onClick={toggle}>
        {busy ? "…" : available ? "Agotar" : "Disponible"}
      </button>
      {error ? <span className="error">{error}</span> : null}
    </div>
  );
}
