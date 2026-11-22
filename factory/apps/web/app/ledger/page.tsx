import Link from "next/link";

import { apiGet } from "@/lib/api";

import { AdjustmentForm } from "./adjustment-form";
import { BalanceView, type BalanceSheet } from "./balance-view";
import { BankReconView, type BankRecon } from "./bank-recon-view";
import { LedgerDownloadHistory } from "./download-history";
import { ExportMenu } from "./export-menu";
import { EXPORT_TARGET, formatExportPeriodLabel } from "./export-links";
import { IncomeView, type IncomeStatement } from "./income-view";
import { JournalPanel } from "./journal-panel";
import { JournalLegend, JournalView, type JournalEntry } from "./journal-view";
import { OwnerSummaryView } from "./owner-summary-view";
import { LedgerFilters, type LedgerFilterValues } from "./ledger-filters";
import { MayorView, type MayorAccount } from "./mayor-view";
import { PeriodClosePanel, type AccountingPeriodRow } from "./period-close";
import { TrialBalanceView, type TrialBalance } from "./trial-balance-view";
import styles from "./ledger.module.css";

type Entry = {
  id: string;
  source: string;
  source_id: string;
  direction: string;
  amount: string;
  currency: string;
  status?: string;
  created_at?: string | null;
  category?: string;
  method?: string;
  reference_label?: string;
  reference_href?: string | null;
};

type SourceTotals = {
  in: string;
  out: string;
  balance: string;
};

type Ledger = {
  period?: { from: string; to: string; preset: string | null };
  in: string;
  out: string;
  balance: string;
  breakdown?: {
    payment?: SourceTotals;
    cash?: SourceTotals;
    purchase?: SourceTotals;
  };
  entries: Entry[];
};

type Journal = {
  period?: { from: string; to: string; preset: string | null };
  entries: JournalEntry[];
};

type MayorPayload = {
  period?: { from: string; to: string; preset: string | null };
  accounts: MayorAccount[];
};

type TrialPayload = TrialBalance & {
  period?: { from: string; to: string; preset: string | null };
};

type IncomePayload = IncomeStatement & {
  period?: { from: string; to: string; preset: string | null };
};

const BREAKDOWN_ORDER = [
  ["payment", "Pago confirmado"],
  ["cash", "Caja"],
  ["purchase", "Compra"],
] as const;

type LedgerView =
  | "hechos"
  | "resumen"
  | "diario"
  | "mayor"
  | "comprobacion"
  | "resultado"
  | "balance"
  | "conciliacion";

type LedgerPageProps = {
  searchParams: Promise<{
    view?: string | string[];
    period?: string | string[];
    from?: string | string[];
    to?: string | string[];
    source?: string | string[];
    status?: string | string[];
    category?: string | string[];
    method?: string | string[];
    account?: string | string[];
  }>;
};

const SOURCE: Record<string, string> = {
  payment: "Pago confirmado",
  cash: "Caja",
  purchase: "Compra",
};

const STATUS: Record<string, string> = {
  recorded: "Vigente",
  voided: "Anulado",
};

const METHOD: Record<string, string> = {
  cash: "Efectivo",
  qr: "QR",
};

const VIEW_CHIPS: { id: LedgerView; label: string }[] = [
  { id: "hechos", label: "Hechos" },
  { id: "resumen", label: "Resumen" },
  { id: "diario", label: "Diario" },
  { id: "mayor", label: "Mayor" },
  { id: "comprobacion", label: "Comprobación" },
  { id: "resultado", label: "Resultado" },
  { id: "balance", label: "Balance" },
  { id: "conciliacion", label: "Conciliación" },
];

function readQuery(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] || "";
  return value || "";
}

function filtersFromParams(
  params: Awaited<LedgerPageProps["searchParams"]>,
): LedgerFilterValues {
  const from = readQuery(params.from);
  const to = readQuery(params.to);
  const period = readQuery(params.period) || (from || to ? "" : "month");
  return {
    period,
    from,
    to,
    source: readQuery(params.source),
    status: readQuery(params.status),
    category: readQuery(params.category),
    method: readQuery(params.method),
  };
}

function ledgerQueryString(filters: LedgerFilterValues): string {
  const params = new URLSearchParams();
  const hasRange = Boolean(filters.from || filters.to);
  if (!hasRange && filters.period) params.set("period", filters.period);
  for (const key of ["from", "to", "source", "status", "category", "method"] as const) {
    if (filters[key]) params.set(key, filters[key]);
  }
  return params.toString();
}

function journalQueryString(
  filters: Pick<LedgerFilterValues, "period" | "from" | "to">,
  account?: string,
): string {
  const params = new URLSearchParams();
  const hasRange = Boolean(filters.from || filters.to);
  if (!hasRange && filters.period) params.set("period", filters.period);
  for (const key of ["from", "to"] as const) {
    if (filters[key]) params.set(key, filters[key]);
  }
  if (account) params.set("account", account);
  return params.toString();
}

function periodHref(preset: string, filters: LedgerFilterValues, view: LedgerView): string {
  const params = new URLSearchParams();
  params.set("view", view);
  params.set("period", preset);
  if (view === "hechos") {
    for (const key of ["source", "status", "category", "method"] as const) {
      if (filters[key]) params.set(key, filters[key]);
    }
  }
  return `/ledger?${params.toString()}`;
}

function viewHref(
  view: LedgerView,
  filters: LedgerFilterValues,
  account?: string,
): string {
  const params = new URLSearchParams();
  params.set("view", view);
  const hasRange = Boolean(filters.from || filters.to);
  if (!hasRange && filters.period) params.set("period", filters.period);
  for (const key of ["from", "to"] as const) {
    if (filters[key]) params.set(key, filters[key]);
  }
  if (view === "hechos") {
    for (const key of ["source", "status", "category", "method"] as const) {
      if (filters[key]) params.set(key, filters[key]);
    }
  }
  if (view === "mayor" && account) params.set("account", account);
  return `/ledger?${params.toString()}`;
}

function formatWhen(raw: string | null | undefined): string {
  if (!raw) return "—";
  const stamp = raw.slice(0, 16).replace("T", " ");
  return stamp || raw;
}

function resolveView(raw: string): LedgerView {
  const value = raw.trim().toLowerCase();
  if (
    value === "resumen" ||
    value === "diario" ||
    value === "mayor" ||
    value === "comprobacion" ||
    value === "resultado" ||
    value === "balance" ||
    value === "conciliacion"
  ) {
    return value;
  }
  return "hechos";
}

function isJournalFamily(view: LedgerView): boolean {
  return (
    view === "resumen" ||
    view === "diario" ||
    view === "mayor" ||
    view === "comprobacion" ||
    view === "resultado" ||
    view === "balance" ||
    view === "conciliacion"
  );
}

export default async function LedgerPage({ searchParams }: LedgerPageProps) {
  const params = await searchParams;
  const view = resolveView(readQuery(params.view));
  const account = readQuery(params.account);
  const filters = filtersFromParams(params);
  const query =
    view === "hechos"
      ? ledgerQueryString(filters)
      : journalQueryString(filters, view === "mayor" ? account : undefined);

  let data: Ledger | null = null;
  let journal: Journal | null = null;
  let mayor: MayorPayload | null = null;
  let trial: TrialPayload | null = null;
  let income: IncomePayload | null = null;
  let balance: (BalanceSheet & { period?: IncomePayload["period"] }) | null = null;
  let recon: (BankRecon & { period?: IncomePayload["period"] }) | null = null;
  let periods: AccountingPeriodRow[] = [];
  let error = "";
  try {
    if (view === "resumen" || view === "diario") {
      journal = await apiGet<Journal>(query ? `/api/journal?${query}` : "/api/journal");
    } else if (view === "mayor") {
      mayor = await apiGet<MayorPayload>(
        query ? `/api/journal/ledger?${query}` : "/api/journal/ledger",
      );
    } else if (view === "comprobacion") {
      trial = await apiGet<TrialPayload>(
        query ? `/api/journal/trial-balance?${query}` : "/api/journal/trial-balance",
      );
    } else if (view === "resultado") {
      income = await apiGet<IncomePayload>(
        query ? `/api/journal/income?${query}` : "/api/journal/income",
      );
    } else if (view === "balance") {
      balance = await apiGet<BalanceSheet & { period?: IncomePayload["period"] }>(
        query ? `/api/journal/balance-sheet?${query}` : "/api/journal/balance-sheet",
      );
    } else if (view === "conciliacion") {
      recon = await apiGet<BankRecon & { period?: IncomePayload["period"] }>(
        query ? `/api/journal/bank-recon?${query}` : "/api/journal/bank-recon",
      );
    } else {
      data = await apiGet<Ledger>(query ? `/api/ledger?${query}` : "/api/ledger");
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  if (isJournalFamily(view)) {
    try {
      const payload = await apiGet<{ periods: AccountingPeriodRow[] }>("/api/journal/periods");
      periods = payload.periods || [];
    } catch {
      periods = [];
    }
  }

  const activePeriod =
    filters.from || filters.to
      ? ""
      : filters.period ||
        data?.period?.preset ||
        journal?.period?.preset ||
        mayor?.period?.preset ||
        trial?.period?.preset ||
        income?.period?.preset ||
        balance?.period?.preset ||
        recon?.period?.preset ||
        "month";
  const periodInfo =
    view === "resumen" || view === "diario"
      ? journal?.period
      : view === "mayor"
        ? mayor?.period
        : view === "comprobacion"
          ? trial?.period
          : view === "resultado"
            ? income?.period
            : view === "balance"
              ? balance?.period
              : view === "conciliacion"
                ? recon?.period
                : data?.period;
  const exportPeriodLabel = formatExportPeriodLabel(
    {
      period: activePeriod || "month",
      from: filters.from,
      to: filters.to,
    },
    periodInfo,
  );

  return (
    <>
      <h1>Contabilidad</h1>
      <p className="lead">
        Libro gerencial: el pago confirmado, la caja y la compra recibida. Una factura
        emitida no confirma un pago.
      </p>
      {isJournalFamily(view) ? (
        <p className="meta">
          Asientos automáticos de partida doble (incluye COGS cuando hay costo de compra). IVA/IT
          diferidos al contador.
        </p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      <div className={styles.periodRow} role="navigation" aria-label="Vista Contabilidad">
        {VIEW_CHIPS.map((chip) => (
          <Link
            key={chip.id}
            href={viewHref(chip.id, { ...filters, period: activePeriod || "month" }, account)}
            className={`${styles.periodChip}${
              view === chip.id ? ` ${styles.periodChipActive}` : ""
            }`}
          >
            {chip.label}
          </Link>
        ))}
      </div>

      <div className={styles.periodRow} role="navigation" aria-label="Período">
        {(
          [
            ["today", "Hoy"],
            ["week", "Semana"],
            ["month", "Mes"],
          ] as const
        ).map(([preset, label]) => (
          <Link
            key={preset}
            href={periodHref(preset, filters, view)}
            className={`${styles.periodChip}${
              activePeriod === preset ? ` ${styles.periodChipActive}` : ""
            }`}
          >
            {label}
          </Link>
        ))}
      </div>

      {isJournalFamily(view) ? (
        <>
          <JournalPanel
            filters={{
              period: activePeriod || "month",
              from: filters.from,
              to: filters.to,
              view,
              account,
            }}
            periodLabel={exportPeriodLabel}
          />
          {view === "conciliacion" ? (
            <ExportMenu
              target={EXPORT_TARGET.CONCILIACION}
              filters={{
                period: activePeriod || "month",
                from: filters.from,
                to: filters.to,
              }}
              periodLabel={exportPeriodLabel}
            />
          ) : null}
          <PeriodClosePanel periods={periods} />
        </>
      ) : (
        <LedgerFilters
          filters={{ ...filters, period: activePeriod || "month" }}
          periodLabel={exportPeriodLabel}
        />
      )}

      {view === "hechos" && data ? (
        <ul className="metrics-grid">
          <li>
            <span className="metrics-label">Ingresos</span>
            <strong>{data.in} BOB</strong>
          </li>
          <li>
            <span className="metrics-label">Egresos</span>
            <strong>{data.out} BOB</strong>
          </li>
          <li>
            <span className="metrics-label">Saldo</span>
            <strong>{data.balance} BOB</strong>
          </li>
        </ul>
      ) : null}

      {periodInfo ? (
        <p className="lead">
          Período {periodInfo.from} → {periodInfo.to}
          {periodInfo.preset ? ` (${periodInfo.preset})` : ""}
        </p>
      ) : null}

      {view === "hechos" && data?.breakdown ? (
        <>
          <h2 className={styles.breakdownTitle}>Desglose por origen</h2>
          <ul className={styles.breakdown}>
            {BREAKDOWN_ORDER.map(([key, label]) => {
              const row = data.breakdown?.[key] || {
                in: "0",
                out: "0",
                balance: "0",
              };
              return (
                <li key={key} className={styles.breakdownItem}>
                  <strong>{label}</strong>
                  <div className={styles.breakdownMeta}>
                    Ingresos {row.in} · Egresos {row.out} · Saldo {row.balance} BOB
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}

      {view === "resumen" ? (
        <>
          <JournalLegend />
          <OwnerSummaryView entries={journal?.entries || []} />
        </>
      ) : null}
      {view === "diario" ? (
        <>
          <JournalLegend />
          <JournalView entries={journal?.entries || []} />
          <AdjustmentForm />
        </>
      ) : null}
      {view === "mayor" ? (
        <MayorView accounts={mayor?.accounts || []} selectedAccount={account || undefined} />
      ) : null}
      {view === "comprobacion" && trial ? (
        <TrialBalanceView
          data={{
            rows: trial.rows || [],
            total_debit: trial.total_debit,
            total_credit: trial.total_credit,
            balanced: trial.balanced,
          }}
        />
      ) : null}
      {view === "resultado" && income ? <IncomeView data={income} /> : null}
      {view === "balance" && balance ? <BalanceView data={balance} /> : null}
      {view === "conciliacion" && recon ? <BankReconView data={recon} /> : null}

      {view === "hechos" ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Origen</th>
                <th>Referencia</th>
                <th>Categoría</th>
                <th>Método</th>
                <th>Sentido</th>
                <th>Monto</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {(data?.entries || []).length === 0 ? (
                <tr>
                  <td colSpan={8}>Todavía no hay asientos en este período.</td>
                </tr>
              ) : (
                data?.entries.map((entry) => {
                  const status = entry.status || "recorded";
                  const refLabel = entry.reference_label || entry.source_id.slice(0, 8);
                  return (
                    <tr
                      key={entry.id}
                      className={status === "voided" ? styles.statusVoided : undefined}
                    >
                      <td>{formatWhen(entry.created_at)}</td>
                      <td>{SOURCE[entry.source] || entry.source}</td>
                      <td>
                        {entry.reference_href ? (
                          <Link className={styles.refLink} href={entry.reference_href}>
                            {refLabel}
                          </Link>
                        ) : (
                          refLabel
                        )}
                      </td>
                      <td className={styles.mutedCell}>{entry.category || "—"}</td>
                      <td>{METHOD[entry.method || ""] || entry.method || "—"}</td>
                      <td>{entry.direction === "in" ? "Ingreso" : "Egreso"}</td>
                      <td>
                        {entry.amount} {entry.currency}
                      </td>
                      <td>{STATUS[status] || status}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      <LedgerDownloadHistory />
    </>
  );
}
