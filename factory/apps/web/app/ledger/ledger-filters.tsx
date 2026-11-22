"use client";

import { useRouter } from "next/navigation";

import { ExportMenu } from "./export-menu";
import { EXPORT_TARGET } from "./export-links";
import styles from "./ledger.module.css";

export type LedgerFilterValues = {
  period: string;
  from: string;
  to: string;
  source: string;
  status: string;
  category: string;
  method: string;
};

function buildLedgerHref(filters: LedgerFilterValues): string {
  const params = new URLSearchParams();
  params.set("view", "hechos");
  const period = filters.period.trim() || "month";
  const hasRange = Boolean(filters.from.trim() || filters.to.trim());
  if (!hasRange) {
    params.set("period", period);
  }
  for (const key of ["from", "to", "source", "status", "category", "method"] as const) {
    const trimmed = filters[key].trim();
    if (trimmed) params.set(key, trimmed);
  }
  const query = params.toString();
  return query ? `/ledger?${query}` : "/ledger?view=hechos";
}

export function LedgerFilters({
  filters,
  periodLabel,
}: {
  filters: LedgerFilterValues;
  periodLabel?: string;
}) {
  const router = useRouter();

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    router.push(
      buildLedgerHref({
        period: String(data.get("period") || filters.period || "month"),
        from: String(data.get("from") || ""),
        to: String(data.get("to") || ""),
        source: String(data.get("source") || ""),
        status: String(data.get("status") || ""),
        category: String(data.get("category") || ""),
        method: String(data.get("method") || ""),
      }),
    );
  }

  function onReset() {
    router.push("/ledger?view=hechos&period=month");
  }

  return (
    <form className={styles.filtersForm} onSubmit={onSubmit} aria-label="Filtros del libro">
      <input type="hidden" name="period" value={filters.period || "month"} />
      <label>
        Origen
        <select name="source" defaultValue={filters.source}>
          <option value="">Todos</option>
          <option value="payment">Pago confirmado</option>
          <option value="cash">Caja</option>
          <option value="purchase">Compra</option>
        </select>
      </label>
      <label>
        Estado
        <select name="status" defaultValue={filters.status}>
          <option value="">Todos</option>
          <option value="recorded">Vigente</option>
          <option value="voided">Anulado</option>
        </select>
      </label>
      <label>
        Categoría
        <input
          name="category"
          type="text"
          defaultValue={filters.category}
          placeholder="venta, compra…"
          autoComplete="off"
        />
      </label>
      <label>
        Método
        <select name="method" defaultValue={filters.method}>
          <option value="">Todos</option>
          <option value="cash">Efectivo</option>
          <option value="qr">QR</option>
        </select>
      </label>
      <label>
        Desde
        <input name="from" type="date" defaultValue={filters.from} />
      </label>
      <label>
        Hasta
        <input name="to" type="date" defaultValue={filters.to} />
      </label>
      <div className={styles.filterActions}>
        <button type="submit">Aplicar</button>
        <button type="button" className="secondary" onClick={onReset}>
          Limpiar
        </button>
      </div>
      <ExportMenu
        target={EXPORT_TARGET.HECHOS}
        filters={{
          period: filters.period,
          from: filters.from,
          to: filters.to,
          source: filters.source,
          status: filters.status,
          category: filters.category,
          method: filters.method,
        }}
        periodLabel={periodLabel}
      />
    </form>
  );
}
