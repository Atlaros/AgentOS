import { Suspense } from "react";

import { apiGet } from "@/lib/api";

import { DirectoryPanel } from "./directory-panel";
import type { SupplierRow } from "./directory-form";
import { OrdersPanel, type PurchaseOrderRow } from "./orders-panel";
import { ReceiveForm } from "./receive-form";
import {
  ReplenishmentPanel,
  type ReplenishmentPayload,
} from "./replenishment-panel";
import { resolveSupplierTab, type SupplierTabId } from "./suppliers-tab";
import { SuppliersTabs } from "./suppliers-tabs";

type SuppliersPageProps = {
  searchParams: Promise<{ tab?: string | string[] }>;
};

function readQuery(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw || "").trim();
}

type CatalogResponse = {
  products: Array<{
    variant_sku: string;
    name: string;
    codigo?: string;
    stock: number;
    supplier_id?: string | null;
    reorder_threshold?: number;
  }>;
};

type SuppliersResponse = {
  suppliers: SupplierRow[];
};

type PurchaseOrdersResponse = {
  purchase_orders: PurchaseOrderRow[];
};

async function ReposicionPanel() {
  let replenishment: ReplenishmentPayload | null = null;
  let suppliers: SupplierRow[] = [];
  let error = "";
  try {
    const [replBody, supplierBody] = await Promise.all([
      apiGet<ReplenishmentPayload>("/api/suppliers/replenishment"),
      apiGet<SuppliersResponse>("/api/suppliers?active_only=true"),
    ]);
    replenishment = replBody;
    suppliers = supplierBody.suppliers || [];
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <p className="lead">
        Reposición agrupada por proveedor, sugerido editable y generación de OC en
        borrador. Abajo sigue el ingreso directo con costo y proveedor.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {replenishment ? <ReplenishmentPanel data={replenishment} /> : null}
      <h2 className="section-title">Ingreso directo</h2>
      <ReceiveForm suppliers={suppliers} />
    </>
  );
}

async function DirectorioContent() {
  let suppliers: SupplierRow[] = [];
  let variants: CatalogResponse["products"] = [];
  let error = "";
  try {
    const [supplierBody, catalogBody] = await Promise.all([
      apiGet<SuppliersResponse>("/api/suppliers?active_only=false"),
      apiGet<CatalogResponse>("/api/catalog?limit=200"),
    ]);
    suppliers = supplierBody.suppliers || [];
    variants = catalogBody.products || [];
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  if (error) return <p className="error">{error}</p>;
  return <DirectoryPanel suppliers={suppliers} variants={variants} />;
}

async function OrdenesContent() {
  let orders: PurchaseOrderRow[] = [];
  let supplierNames: Record<string, string> = {};
  let error = "";
  try {
    const [poBody, supplierBody] = await Promise.all([
      apiGet<PurchaseOrdersResponse>("/api/purchase-orders"),
      apiGet<SuppliersResponse>("/api/suppliers?active_only=false"),
    ]);
    orders = poBody.purchase_orders || [];
    supplierNames = Object.fromEntries(
      (supplierBody.suppliers || []).map((row) => [row.id, row.name]),
    );
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  if (error) return <p className="error">{error}</p>;
  return <OrdersPanel orders={orders} supplierNames={supplierNames} />;
}

export default async function SuppliersPage({ searchParams }: SuppliersPageProps) {
  const params = await searchParams;
  const activeTab: SupplierTabId = resolveSupplierTab(readQuery(params.tab));

  return (
    <>
      <h1>Proveedores</h1>
      <Suspense fallback={<p className="meta">Cargando…</p>}>
        <SuppliersTabs activeTab={activeTab} />
      </Suspense>
      {activeTab === "directorio" ? <DirectorioContent /> : null}
      {activeTab === "reposicion" ? <ReposicionPanel /> : null}
      {activeTab === "ordenes" ? <OrdenesContent /> : null}
    </>
  );
}
