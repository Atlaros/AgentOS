"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import styles from "./catalog.module.css";

export function StockCell({ variantSku, stock }: { variantSku: string; stock: number }) {
  const router = useRouter();
  const [value, setValue] = useState(String(stock));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setValue(String(stock));
  }, [stock]);

  async function save(nextRaw: string) {
    const next = Number(nextRaw);
    if (!Number.isInteger(next) || next < 0) {
      setError("Stock inválido");
      setValue(String(stock));
      return;
    }
    if (next === stock) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(
        `/api/backend/api/catalog/${encodeURIComponent(variantSku)}/availability`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ available: next > 0, stock: next }),
        },
      );
      if (!res.ok) {
        setError("No se pudo guardar");
        setValue(String(stock));
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudo guardar");
      setValue(String(stock));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.stockCell}>
      <input
        className={styles.stockInput}
        type="number"
        min={0}
        step={1}
        value={value}
        disabled={busy}
        aria-label={`Stock de ${variantSku}`}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => void save(value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            (event.target as HTMLInputElement).blur();
          }
        }}
      />
      {error ? <span className={styles.stockError}>{error}</span> : null}
    </div>
  );
}
