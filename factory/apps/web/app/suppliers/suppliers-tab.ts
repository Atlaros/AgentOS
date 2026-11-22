/** Shared tab helpers — safe for Server and Client Components. */

export const SUPPLIER_TAB_IDS = ["directorio", "reposicion", "ordenes"] as const;

export type SupplierTabId = (typeof SUPPLIER_TAB_IDS)[number];

export function isSupplierTabId(value: string | null | undefined): value is SupplierTabId {
  return value === "directorio" || value === "reposicion" || value === "ordenes";
}

export function resolveSupplierTab(raw: string | null | undefined): SupplierTabId {
  if (isSupplierTabId(raw)) return raw;
  return "directorio";
}

export function supplierHref(tab: SupplierTabId): string {
  return `/suppliers?tab=${tab}`;
}
