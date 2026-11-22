"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import styles from "./suppliers.module.css";
import {
  SUPPLIER_TAB_IDS,
  supplierHref,
  type SupplierTabId,
} from "./suppliers-tab";

export type { SupplierTabId } from "./suppliers-tab";
export {
  SUPPLIER_TAB_IDS,
  isSupplierTabId,
  resolveSupplierTab,
  supplierHref,
} from "./suppliers-tab";

const TAB_LABELS: Record<SupplierTabId, string> = {
  directorio: "Directorio",
  reposicion: "Reposición",
  ordenes: "Órdenes",
};

export function SuppliersTabs({ activeTab }: { activeTab: SupplierTabId }) {
  const searchParams = useSearchParams();
  void searchParams;

  return (
    <nav className={styles.tabNav} aria-label="Secciones de proveedores">
      <div className={styles.tabList} role="tablist">
        {SUPPLIER_TAB_IDS.map((tab) => {
          const selected = tab === activeTab;
          return (
            <Link
              key={tab}
              href={supplierHref(tab)}
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
