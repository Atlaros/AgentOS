"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { CashFilters, type CashFilterValues } from "./cash-filters";
import { CashForm } from "./cash-form";
import { CashTabs, cashHref, resolveCashTab } from "./cash-tabs";
import styles from "./cash.module.css";
import { CloseHistory } from "./close-history";
import { MovementsTable, type CashActivityEntry } from "./movements-table";
import { SessionPanel, type CashSession } from "./session-panel";
import { WalkinSale } from "./walkin-sale";

export type CashWorkspaceProps = {
  filters: CashFilterValues;
  session: CashSession | null;
  open: boolean;
  opening: string;
  cashIn: string;
  cashOut: string;
  expected: string;
  qrIn: string | null;
  entries: CashActivityEntry[];
  count: number | undefined;
  note: string | undefined;
  closes: CashSession[];
  sessions: CashSession[];
};

function moneyLabel(value: string): string {
  return value === "—" ? value : `${value} BOB`;
}

export function CashWorkspace({
  filters,
  session,
  open,
  opening,
  cashIn,
  cashOut,
  expected,
  qrIn,
  entries,
  count,
  note,
  closes,
  sessions,
}: CashWorkspaceProps) {
  const searchParams = useSearchParams();
  const hasBookFilters = Object.values(filters).some(Boolean);
  const activeTab = resolveCashTab(searchParams.get("tab"), hasBookFilters);

  return (
    <>
      <CashTabs activeTab={activeTab} />
      <div
        role="tabpanel"
        id={`cash-panel-${activeTab}`}
        aria-label={
          activeTab === "sale"
            ? "Venta mostrador"
            : activeTab === "shift"
              ? "Turno"
              : "Movimientos"
        }
      >
        {activeTab === "sale" ? (
          open ? (
            <WalkinSale />
          ) : (
            <section className={styles.panel} aria-labelledby="cash-sale-closed-title">
              <h2 id="cash-sale-closed-title" className={styles.panelTitle}>
                Caja cerrada
              </h2>
              <p className={styles.panelLead}>Abrí la caja para vender.</p>
              <Link
                href={cashHref("shift", searchParams)}
                className={styles.tabAction}
                scroll={false}
              >
                Ir a Turno
              </Link>
            </section>
          )
        ) : null}

        {activeTab === "shift" ? (
          <>
            <SessionPanel session={session} hasHistory={closes.length > 0} />
            <ul className="metrics-grid">
              <li>
                <span className="metrics-label">Saldo inicial</span>
                <strong className={styles.num}>{moneyLabel(opening)}</strong>
              </li>
              <li>
                <span className="metrics-label">Entradas</span>
                <strong className={styles.num}>{moneyLabel(cashIn)}</strong>
              </li>
              <li>
                <span className="metrics-label">Salidas</span>
                <strong className={styles.num}>{moneyLabel(cashOut)}</strong>
              </li>
              <li>
                <span className="metrics-label">Saldo esperado</span>
                <strong className={styles.num}>{moneyLabel(expected)}</strong>
              </li>
              {qrIn ? (
                <li>
                  <span className="metrics-label">QR cobrado</span>
                  <strong className={styles.num}>{qrIn} BOB</strong>
                </li>
              ) : null}
            </ul>
            <div className={styles.historyBlock}>
              <CloseHistory closes={closes} />
            </div>
          </>
        ) : null}

        {activeTab === "movements" ? (
          <>
            {open ? <CashForm /> : null}
            <CashFilters filters={filters} sessions={sessions} />
            <MovementsTable entries={entries} count={count} />
            {note ? <p className="meta">{note}</p> : null}
          </>
        ) : null}
      </div>
    </>
  );
}
