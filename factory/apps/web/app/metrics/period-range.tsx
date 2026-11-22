"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./metrics.module.css";

function shiftDate(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const stamp = new Date(Date.UTC(year, month - 1, day));
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
}

export function PeriodRangeForm({ from, to }: { from: string; to: string }) {
  const router = useRouter();
  const [error, setError] = useState("");

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const dateFrom = String(data.get("date_from") || "");
    const dateTo = String(data.get("date_to") || "");
    if (!dateFrom || !dateTo || dateTo < dateFrom) {
      setError("El día final no puede ser anterior al inicial.");
      return;
    }
    setError("");
    const params = new URLSearchParams({
      period: "range",
      date_from: `${dateFrom}T00:00:00+00:00`,
      date_to: `${shiftDate(dateTo, 1)}T00:00:00+00:00`,
    });
    router.push(`/metrics?${params.toString()}`);
  }

  return (
    <form className={styles.range} onSubmit={onSubmit}>
      <label>
        Desde
        <input name="date_from" type="date" defaultValue={from} required />
      </label>
      <label>
        Hasta
        <input name="date_to" type="date" defaultValue={to} required />
      </label>
      <button type="submit">Ver rango</button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
