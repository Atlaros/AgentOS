"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import styles from "./cash.module.css";

export const CASH_TAB_IDS = ["sale", "shift", "movements"] as const;

export type CashTabId = (typeof CASH_TAB_IDS)[number];

const TAB_LABELS: Record<CashTabId, string> = {
  sale: "Venta mostrador",
  shift: "Turno",
  movements: "Movimientos",
};

export function isCashTabId(value: string | null | undefined): value is CashTabId {
  return value === "sale" || value === "shift" || value === "movements";
}

export function resolveCashTab(
  raw: string | null | undefined,
  hasBookFilters = false,
): CashTabId {
  if (raw === "book") return "movements";
  if (isCashTabId(raw)) return raw;
  if (!raw && hasBookFilters) return "movements";
  return "sale";
}

export function cashHref(tab: CashTabId, current: URLSearchParams): string {
  const next = new URLSearchParams(current.toString());
  next.set("tab", tab);
  const query = next.toString();
  return query ? `/cash?${query}` : `/cash?tab=${tab}`;
}

export function CashTabs({ activeTab }: { activeTab: CashTabId }) {
  const searchParams = useSearchParams();

  return (
    <nav className={styles.tabNav} aria-label="Secciones de caja">
      <div className={styles.tabList} role="tablist">
        {CASH_TAB_IDS.map((tab) => {
          const selected = tab === activeTab;
          return (
            <Link
              key={tab}
              href={cashHref(tab, searchParams)}
              role="tab"
              aria-selected={selected}
              className={selected ? styles.tabSelected : styles.tab}
              scroll={false}
            >
              {TAB_LABELS[tab]}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
