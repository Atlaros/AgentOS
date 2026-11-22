"use client";

import { useRouter } from "next/navigation";

import { ExportMenu } from "./export-menu";
import { EXPORT_TARGET, type ExportTarget } from "./export-links";
import styles from "./ledger.module.css";

export type JournalFilterValues = {
  period: string;
  from: string;
  to: string;
  view: string;
  account?: string;
};

const ACCOUNT_OPTIONS = [
  { value: "", label: "Todas las cuentas" },
  { value: "1100", label: "1100 Caja" },
  { value: "1200", label: "1200 Banco" },
  { value: "1300", label: "1300 Inventario" },
  { value: "1400", label: "1400 Cuentas por cobrar" },
  { value: "2100", label: "2100 Cuentas por pagar" },
  { value: "4100", label: "4100 Ventas" },
  { value: "5100", label: "5100 Gastos operativos" },
  { value: "5110", label: "5110 Costo de ventas" },
  { value: "5200", label: "5200 Retiros del dueño" },
] as const;

const VIEW_EXPORT_TARGET: Record<string, ExportTarget> = {
  resumen: EXPORT_TARGET.DIARIO,
  diario: EXPORT_TARGET.DIARIO,
  mayor: EXPORT_TARGET.MAYOR,
  comprobacion: EXPORT_TARGET.COMPROBACION,
  resultado: EXPORT_TARGET.RESULTADO,
  balance: EXPORT_TARGET.BALANCE,
};

function buildJournalHref(filters: JournalFilterValues): string {
  const params = new URLSearchParams();
  const view = filters.view.trim() || "diario";
  params.set("view", view);
  const period = filters.period.trim() || "month";
  const hasRange = Boolean(filters.from.trim() || filters.to.trim());
  if (!hasRange) {
    params.set("period", period);
  }
  for (const key of ["from", "to"] as const) {
    const trimmed = filters[key].trim();
    if (trimmed) params.set(key, trimmed);
  }
  if (view === "mayor") {
    const account = (filters.account || "").trim();
    if (account) params.set("account", account);
  }
  return `/ledger?${params.toString()}`;
}

export function JournalPanel({
  filters,
  periodLabel,
}: {
  filters: JournalFilterValues;
  periodLabel?: string;
}) {
  const router = useRouter();
  const view = filters.view || "diario";
  const showAccount = view === "mayor";
  const exportTarget = VIEW_EXPORT_TARGET[view];
  const filtersAriaLabel = view === "resumen" ? "Filtros del resumen" : "Filtros del diario";

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    router.push(
      buildJournalHref({
        period: String(data.get("period") || filters.period || "month"),
        from: String(data.get("from") || ""),
        to: String(data.get("to") || ""),
        view,
        account: String(data.get("account") || ""),
      }),
    );
  }

  function onReset() {
    router.push(`/ledger?view=${encodeURIComponent(view)}&period=month`);
  }

  return (
    <form className={styles.filtersForm} onSubmit={onSubmit} aria-label={filtersAriaLabel}>
      <input type="hidden" name="period" value={filters.period || "month"} />
      {showAccount ? (
        <label>
          Cuenta
          <select name="account" defaultValue={filters.account || ""}>
            {ACCOUNT_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
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
      {exportTarget ? (
        <ExportMenu
          target={exportTarget}
          filters={{
            period: filters.period,
            from: filters.from,
            to: filters.to,
            account: filters.account,
          }}
          periodLabel={periodLabel}
        />
      ) : null}
    </form>
  );
}
