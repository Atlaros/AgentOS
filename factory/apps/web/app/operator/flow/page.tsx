import Link from "next/link";
import { apiGet } from "@/lib/api";
import {
  FlowBoard,
  type CatalogRule,
  type CompatibleMap,
  type EmployeePaletteItem,
  type FlowEdge,
  type FlowNode,
  type PositionMap,
} from "./flow-board";

type Props = { searchParams?: Promise<{ tenant_id?: string }> };

export default async function OperatorFlowPage({ searchParams }: Props) {
  const params = (await searchParams) ?? {};
  const tenantId = (params.tenant_id || "").trim();
  let nodes: FlowNode[] = [];
  let edges: FlowEdge[] = [];
  let rules: CatalogRule[] = [];
  let compatible: CompatibleMap = {};
  let positions: PositionMap = {};
  let palette: string[] = [];
  let employeePalette: EmployeePaletteItem[] = [];
  let published = false;
  let publishedKinds: string[] | null = null;
  let error = "";
  try {
    if (!tenantId) {
      throw new Error("Elegí un negocio en Operador → Lienzo para abrir su mapa.");
    }
    const flowPath = `/api/operator/flow-map?tenant_id=${encodeURIComponent(tenantId)}`;
    const [flow, listed] = await Promise.all([
      apiGet<{
        nodes: FlowNode[];
        edges: FlowEdge[];
        compatible: CompatibleMap;
        positions: PositionMap;
        palette: string[];
        employee_palette?: EmployeePaletteItem[];
        published?: boolean;
        published_kinds?: string[] | null;
      }>(flowPath),
      apiGet<{ rules: CatalogRule[] }>("/api/operator/rules"),
    ]);
    nodes = flow.nodes;
    edges = flow.edges;
    compatible = flow.compatible ?? {};
    positions = flow.positions ?? {};
    palette = flow.palette ?? [];
    employeePalette = flow.employee_palette ?? [];
    published = Boolean(flow.published);
    publishedKinds = flow.published_kinds ?? null;
    rules = listed.rules;
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }

  return (
    <>
      <p className="meta" style={{ marginBottom: "0.75rem" }}>
        <Link href="/operator?tab=lienzo">← Negocios / Lienzo</Link>
      </p>
      {error ? (
        <p className="error">{error}</p>
      ) : (
        <FlowBoard
          nodes={nodes}
          edges={edges}
          rules={rules}
          compatible={compatible}
          positions={positions}
          palette={palette}
          employeePalette={employeePalette}
          tenantId={tenantId}
          published={published}
          publishedKinds={publishedKinds}
        />
      )}
    </>
  );
}
