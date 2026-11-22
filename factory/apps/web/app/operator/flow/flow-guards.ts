/** Client-side canvas guards. Server validation stays authoritative. */

export type CompatibleMap = Record<string, Record<string, string[]>>;

export type SelectedCanvasNode = {
  id: string;
  kind: string;
  locked: boolean;
  label: string;
};

export function canConnect(
  compatible: CompatibleMap,
  port: string,
  source: string | null | undefined,
  target: string | null | undefined,
): boolean {
  if (!source || !target || source === target) return false;
  const targets = compatible[source]?.[port] ?? [];
  return targets.includes(target);
}

export function isCanvasItemDeletable(locked: boolean): boolean {
  return !locked;
}

/** Order + Collections must stay on any publishable canvas (server enforces too). */
export function hasLockedCore(kinds: Iterable<string>): boolean {
  const set = new Set(Array.from(kinds, (item) => String(item).trim()).filter(Boolean));
  return set.has("pedido") && set.has("cobros");
}

export function outboundPorts(compatible: CompatibleMap, kind: string): string[] {
  return Object.keys(compatible[kind] ?? {}).sort();
}

/**
 * Propose kinds to add without publishing. Keeps existing order; fills locked core
 * and optional palette modules that are still missing.
 */
export type TeamAssignment = { employee_key: string; module: string };

export function isEmployeeNodeId(id: string | null | undefined): boolean {
  return Boolean(id && String(id).startsWith("emp:"));
}

export function employeeKeyFromNodeId(id: string): string {
  return String(id).replace(/^emp:/, "");
}

export function moduleKindsOnly(kinds: Iterable<string>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of kinds) {
    const kind = String(raw).trim();
    if (!kind || kind === "employee" || isEmployeeNodeId(kind) || seen.has(kind)) continue;
    seen.add(kind);
    out.push(kind);
  }
  return out;
}

export function canAssignEmployee(allowedModules: Iterable<string>, target: string | null | undefined): boolean {
  if (!target || isEmployeeNodeId(target)) return false;
  return new Set(Array.from(allowedModules, String)).has(target);
}

export function teamFromEdges(
  edges: Iterable<{ source: string; target: string; port?: string }>,
): TeamAssignment[] {
  const seen = new Set<string>();
  const out: TeamAssignment[] = [];
  for (const edge of edges) {
    if (!isEmployeeNodeId(edge.source)) continue;
    if ((edge.port || "equipo") !== "equipo") continue;
    const key = employeeKeyFromNodeId(edge.source);
    const module = String(edge.target || "").trim();
    if (!key || !module) continue;
    const pair = `${key}→${module}`;
    if (seen.has(pair)) continue;
    seen.add(pair);
    out.push({ employee_key: key, module });
  }
  return out;
}

export function proposeCanvasKinds(
  currentKinds: Iterable<string>,
  palette: Iterable<string>,
): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const raw of currentKinds) {
    const kind = String(raw).trim();
    if (!kind || seen.has(kind)) continue;
    seen.add(kind);
    ordered.push(kind);
  }
  for (const required of ["pedido", "cobros"] as const) {
    if (!seen.has(required)) {
      seen.add(required);
      ordered.push(required);
    }
  }
  for (const raw of palette) {
    const kind = String(raw).trim();
    if (!kind || seen.has(kind)) continue;
    seen.add(kind);
    ordered.push(kind);
  }
  return ordered;
}
