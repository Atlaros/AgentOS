"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  canAssignEmployee,
  canConnect,
  employeeKeyFromNodeId,
  hasLockedCore,
  isCanvasItemDeletable,
  isEmployeeNodeId,
  moduleKindsOnly,
  outboundPorts,
  teamFromEdges,
  type CompatibleMap,
  type SelectedCanvasNode,
  type TeamAssignment,
} from "./flow-guards";
import { FlowPropertiesPanel } from "./flow-properties";
import styles from "./flow-board.module.css";

export type FlowNode = {
  id: string;
  kind: string;
  locked: boolean;
  family?: "module" | "employee";
  employee_key?: string | null;
  display_name?: string | null;
  base_role?: string | null;
};
export type FlowEdge = { source: string; target: string; port: string; locked: boolean };
export type EmployeePaletteItem = {
  employee_key: string;
  display_name: string;
  base_role: string;
  modules?: string[];
};
export type CatalogRule = {
  id: string;
  when_event: string;
  if_threshold: string;
  then_action: string;
  status: string;
  version?: number;
};
export type PositionMap = Record<string, { x: number; y: number }>;
export type { CompatibleMap };

type ModuleData = {
  kind: string;
  locked: boolean;
  label: string;
  tone: string;
  blurb: string;
  family: "module" | "employee";
  employeeKey?: string;
  baseRole?: string;
  modules?: string[];
};

type ModuleFlowNode = Node<ModuleData, "module" | "employee">;

type Tone = "channel" | "path" | "ops" | "books" | "read";

const NAMES: Record<string, string> = {
  whatsapp: "WhatsApp",
  mostrador: "Mostrador",
  pedido: "Pedido",
  cobros: "Cobros",
  caja: "Caja",
  contabilidad: "Contabilidad",
  proveedores: "Proveedores",
  aprobacion: "Aprobación",
  catalogo: "Catálogo",
  analitica: "Analítica",
  reportes: "Reportes",
  conocimiento: "Conocimiento",
};

const BLURBS: Record<string, string> = {
  whatsapp: "Canal con el cliente",
  mostrador: "Venta en el local",
  pedido: "Arma el pedido",
  cobros: "Cobra y confirma el pago",
  caja: "Movimientos de caja",
  contabilidad: "Asientos del negocio",
  proveedores: "Compras a proveedores",
  aprobacion: "OK humano cuando hace falta",
  catalogo: "Productos y precios",
  analitica: "Lectura del negocio",
  reportes: "Reportes para el dueño",
  conocimiento: "Preguntas frecuentes",
};

const TONE_BY_KIND: Record<string, Tone> = {
  whatsapp: "channel",
  mostrador: "channel",
  pedido: "path",
  cobros: "path",
  caja: "ops",
  proveedores: "ops",
  aprobacion: "ops",
  catalogo: "ops",
  contabilidad: "books",
  analitica: "read",
  reportes: "read",
  conocimiento: "read",
};

const CATALOG_GROUPS: { title: string; kinds: string[] }[] = [
  { title: "Canales", kinds: ["whatsapp", "mostrador"] },
  { title: "Camino de venta", kinds: ["pedido", "cobros"] },
  { title: "Operaciones", kinds: ["caja", "catalogo", "proveedores", "aprobacion"] },
  { title: "Libros", kinds: ["contabilidad"] },
  { title: "Lectura", kinds: ["analitica", "reportes", "conocimiento"] },
];

const ORDER = [
  "whatsapp",
  "mostrador",
  "pedido",
  "cobros",
  "caja",
  "contabilidad",
  "proveedores",
  "aprobacion",
];

function label(id: string): string {
  return NAMES[id] || id;
}

function toneFor(id: string): Tone {
  return TONE_BY_KIND[id] || "ops";
}

function blurbFor(id: string): string {
  return BLURBS[id] || "Módulo del negocio";
}

function ruleError(status: number, detail: string): string {
  if (detail === "payment_confirm_forbidden") return "Una regla no puede confirmar un pago.";
  if (detail === "rule_incomplete") return "Hacen falta Cuando, Si y Entonces.";
  if (detail === "path_locked") return "Pedido y Cobros se quedan en el camino.";
  if (detail === "port_mismatch") return "Esos módulos no comparten ese puerto.";
  if (status === 401 || status === 403) return "La sesión de operador no puede guardar esta regla.";
  return "No se guardó la regla.";
}

function ModuleNode({ data }: NodeProps<ModuleFlowNode>) {
  const isEmployee = data.family === "employee";
  return (
    <div
      className={[styles.node, data.locked ? styles.nodeLocked : "", isEmployee ? styles.nodeEmployee : ""]
        .filter(Boolean)
        .join(" ")}
      data-tone={isEmployee ? "channel" : data.tone}
    >
      {isEmployee ? null : <Handle type="target" position={Position.Left} className={styles.handle} />}
      <div className={styles.nodeBody}>
        <div className={styles.nodeCopy}>
          <span className={styles.nodeName}>{data.label}</span>
          <span className={styles.nodeKind}>{data.blurb}</span>
        </div>
        {data.locked ? <span className={styles.lock}>Fijo</span> : null}
        {isEmployee ? <span className={styles.lock}>Equipo</span> : null}
      </div>
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </div>
  );
}

const nodeTypes = { module: ModuleNode, employee: ModuleNode };

function toFlowNodes(
  nodes: FlowNode[],
  positions: PositionMap,
  employeePalette: EmployeePaletteItem[] = [],
): ModuleFlowNode[] {
  const byKey = new Map(employeePalette.map((item) => [item.employee_key, item]));
  return nodes.map((node, index) => {
    const isEmployee = node.family === "employee" || node.kind === "employee" || isEmployeeNodeId(node.id);
    const spot = positions[node.id] ?? {
      x: 48 + (index % 3) * 220,
      y: 48 + Math.floor(index / 3) * 110,
    };
    const key = isEmployee ? node.employee_key || employeeKeyFromNodeId(node.id) : "";
    const meta = key ? byKey.get(key) : undefined;
    const display = isEmployee
      ? node.display_name || meta?.display_name || key
      : label(node.kind);
    return {
      id: node.id,
      type: (isEmployee ? "employee" : "module") as "module" | "employee",
      position: spot,
      data: {
        kind: isEmployee ? "employee" : node.kind,
        locked: node.locked,
        label: display,
        tone: isEmployee ? "channel" : toneFor(node.kind),
        blurb: isEmployee ? `Rol · ${node.base_role || meta?.base_role || "equipo"}` : blurbFor(node.kind),
        family: isEmployee ? "employee" : "module",
        employeeKey: isEmployee ? key : undefined,
        baseRole: node.base_role || meta?.base_role || undefined,
        modules: meta?.modules || [],
      },
      deletable: isCanvasItemDeletable(node.locked),
      draggable: true,
    };
  });
}

function toFlowEdges(edges: FlowEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: `${edge.source}-${edge.target}-${edge.port}`,
    source: edge.source,
    target: edge.target,
    label: edge.port,
    deletable: isCanvasItemDeletable(edge.locked),
    data: { port: edge.port, locked: edge.locked },
    className: edge.locked ? styles.wireLocked : styles.wire,
  }));
}

function FlowCanvas({
  initialNodes,
  initialEdges,
  positions,
  compatible,
  palette,
  employeePalette,
  port,
  placeKinds,
  onPortMismatch,
  onConnected,
  onPlaced,
  onSelectionChange,
  onKindsChange,
  onTeamChange,
  onEmployeeKeysChange,
  onPlaceKindsApplied,
  onUnusedPalette,
}: {
  initialNodes: FlowNode[];
  initialEdges: FlowEdge[];
  positions: PositionMap;
  compatible: CompatibleMap;
  palette: string[];
  employeePalette: EmployeePaletteItem[];
  port: string;
  placeKinds: string[] | null;
  onPortMismatch: () => void;
  onConnected: (edge: FlowEdge) => void;
  onPlaced: (kind: string) => void;
  onSelectionChange: (node: SelectedCanvasNode | null) => void;
  onKindsChange: (kinds: string[]) => void;
  onTeamChange: (team: TeamAssignment[]) => void;
  onEmployeeKeysChange: (keys: string[]) => void;
  onPlaceKindsApplied: () => void;
  onUnusedPalette: (kinds: string[]) => void;
}) {
  const { screenToFlowPosition } = useReactFlow();
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<ModuleFlowNode>(
    toFlowNodes(initialNodes, positions, employeePalette),
  );
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState(toFlowEdges(initialEdges));
  const [paletteDrag, setPaletteDrag] = useState("");

  const seedKey = useMemo(
    () =>
      `${initialNodes.map((n) => `${n.id}:${n.locked}`).join(",")}|${initialEdges
        .map((e) => `${e.source}-${e.target}-${e.port}:${e.locked}`)
        .join(",")}`,
    [initialNodes, initialEdges],
  );

  useEffect(() => {
    setNodes(toFlowNodes(initialNodes, positions, employeePalette));
    setEdges(toFlowEdges(initialEdges));
  }, [seedKey, initialNodes, initialEdges, positions, employeePalette, setNodes, setEdges]);

  useEffect(() => {
    onKindsChange(
      moduleKindsOnly(
        nodes.filter((node) => node.data.family !== "employee").map((node) => node.data.kind),
      ),
    );
  }, [nodes, onKindsChange]);

  useEffect(() => {
    onTeamChange(
      teamFromEdges(
        edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          port: String((edge.data as { port?: string } | undefined)?.port || edge.label || ""),
        })),
      ),
    );
  }, [edges, onTeamChange]);

  useEffect(() => {
    onEmployeeKeysChange(
      nodes
        .filter((node) => node.data.family === "employee")
        .map((node) => node.data.employeeKey || employeeKeyFromNodeId(node.id)),
    );
  }, [nodes, onEmployeeKeysChange]);

  useEffect(() => {
    if (!placeKinds || placeKinds.length === 0) return;
    setNodes((current) => {
      const have = new Set(current.map((node) => node.id));
      const additions: ModuleFlowNode[] = [];
      placeKinds.forEach((kind, index) => {
        if (have.has(kind)) return;
        const locked = kind === "pedido" || kind === "cobros";
        additions.push({
          id: kind,
          type: "module",
          position: {
            x: 48 + ((current.length + index) % 3) * 220,
            y: 48 + Math.floor((current.length + index) / 3) * 110,
          },
          data: {
            kind,
            locked,
            label: label(kind),
            tone: toneFor(kind),
            blurb: blurbFor(kind),
            family: "module",
          },
          deletable: isCanvasItemDeletable(locked),
        });
      });
      return additions.length === 0 ? current : [...current, ...additions];
    });
    onPlaceKindsApplied();
  }, [placeKinds, onPlaceKindsApplied, setNodes]);

  const placedIds = useMemo(() => new Set(nodes.map((node) => node.id)), [nodes]);
  const unusedPalette = useMemo(
    () => palette.filter((item) => !placedIds.has(item)),
    [palette, placedIds],
  );
  const unusedKey = unusedPalette.join(",");

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      const from = connection.source;
      const to = connection.target;
      if (isEmployeeNodeId(from)) {
        const sourceNode = nodes.find((node) => node.id === from);
        const allowed = sourceNode?.data.modules || [];
        return canAssignEmployee(allowed, to);
      }
      return canConnect(compatible, port, from, to);
    },
    [compatible, port, nodes],
  );

  const onNodesChange: OnNodesChange<ModuleFlowNode> = useCallback(
    (changes) => {
      const filtered = changes.filter((change) => {
        if (change.type !== "remove") return true;
        const node = nodes.find((item) => item.id === change.id);
        return node ? node.deletable !== false : true;
      });
      onNodesChangeBase(filtered);
    },
    [nodes, onNodesChangeBase],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => {
      const filtered = changes.filter((change) => {
        if (change.type !== "remove") return true;
        const edge = edges.find((item) => item.id === change.id);
        return edge ? edge.deletable !== false : true;
      });
      onEdgesChangeBase(filtered);
    },
    [edges, onEdgesChangeBase],
  );

  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (!isValidConnection(connection)) {
        onPortMismatch();
        return;
      }
      const from = connection.source!;
      const to = connection.target!;
      const linkPort = isEmployeeNodeId(from) ? "equipo" : port;
      setEdges((current) =>
        addEdge(
          {
            ...connection,
            id: `${from}-${to}-${linkPort}`,
            label: linkPort,
            deletable: true,
            data: { port: linkPort, locked: false },
          },
          current,
        ),
      );
      onConnected({ source: from, target: to, port: linkPort, locked: false });
    },
    [isValidConnection, onConnected, onPortMismatch, port, setEdges],
  );

  function dropPalette(event: React.DragEvent<HTMLDivElement>) {
    const employeeRaw = event.dataTransfer.getData("application/x-factory-employee");
    if (employeeRaw) {
      event.preventDefault();
      setPaletteDrag("");
      let item: EmployeePaletteItem;
      try {
        item = JSON.parse(employeeRaw) as EmployeePaletteItem;
      } catch {
        return;
      }
      const nodeId = `emp:${item.employee_key}`;
      if (placedIds.has(nodeId)) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setNodes((current) => [
        ...current,
        {
          id: nodeId,
          type: "employee",
          position,
          data: {
            kind: "employee",
            locked: false,
            label: item.display_name,
            tone: "channel",
            blurb: `Rol · ${item.base_role}`,
            family: "employee",
            employeeKey: item.employee_key,
            baseRole: item.base_role,
            modules: item.modules || [],
          },
          deletable: true,
        },
      ]);
      onPlaced(item.display_name);
      return;
    }
    const kind = event.dataTransfer.getData("application/x-factory-palette") || paletteDrag;
    if (!kind) return;
    event.preventDefault();
    setPaletteDrag("");
    if (!palette.includes(kind) || placedIds.has(kind)) return;
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const locked = kind === "pedido" || kind === "cobros";
    setNodes((current) => [
      ...current,
      {
        id: kind,
        type: "module",
        position,
        data: {
          kind,
          locked,
          label: label(kind),
          tone: toneFor(kind),
          blurb: blurbFor(kind),
          family: "module",
        },
        deletable: isCanvasItemDeletable(locked),
      },
    ]);
    onPlaced(kind);
  }

  useEffect(() => {
    onUnusedPalette(unusedPalette);
    // Only re-notify when the kind set changes — not when the parent recreates the callback.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unusedKey is the intentional signal
  }, [unusedKey]);

  return (
    <div
      className={styles.canvas}
      data-testid="flow-canvas"
      onDragOver={(event) => {
        const types = event.dataTransfer.types;
        if (
          !paletteDrag &&
          !types.includes("application/x-factory-palette") &&
          !types.includes("application/x-factory-employee")
        ) {
          return;
        }
        event.preventDefault();
      }}
      onDrop={dropPalette}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onSelectionChange={({ nodes: selected }) => {
          const first = selected[0];
          if (!first) {
            onSelectionChange(null);
            return;
          }
          const data = first.data as ModuleData;
          onSelectionChange({
            id: first.id,
            kind: data.kind,
            locked: data.locked,
            label: data.label,
          });
        }}
        isValidConnection={isValidConnection}
        fitView
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Lines} gap={28} color="#3a342e" />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}

export function FlowBoard({
  nodes: initialNodes,
  edges,
  rules,
  compatible,
  positions: initialPositions,
  palette,
  employeePalette = [],
  tenantId,
  published = false,
  publishedKinds = null,
}: {
  nodes: FlowNode[];
  edges: FlowEdge[];
  rules: CatalogRule[];
  compatible: CompatibleMap;
  positions: PositionMap;
  palette: string[];
  employeePalette?: EmployeePaletteItem[];
  tenantId: string;
  published?: boolean;
  publishedKinds?: string[] | null;
}) {
  const router = useRouter();
  const [whenEvent, setWhenEvent] = useState("");
  const [ifThreshold, setIfThreshold] = useState("");
  const [thenAction, setThenAction] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [publishingId, setPublishingId] = useState("");
  const [source, setSource] = useState("cobros");
  const [target, setTarget] = useState("caja");
  const [port, setPort] = useState("pago_confirmado");
  const [notice, setNotice] = useState("");
  const [replacement, setReplacement] = useState("");
  const [selected, setSelected] = useState<SelectedCanvasNode | null>(null);
  const [canvasKinds, setCanvasKinds] = useState<string[]>(() =>
    initialNodes.map((node) => node.kind),
  );
  const [placeKinds, setPlaceKinds] = useState<string[] | null>(null);
  const [proposal, setProposal] = useState<string[] | null>(null);
  const [mapBusy, setMapBusy] = useState(false);
  const [unusedPalette, setUnusedPalette] = useState<string[]>(palette);
  const [team, setTeam] = useState<TeamAssignment[]>([]);
  const [employeeKeysOnCanvas, setEmployeeKeysOnCanvas] = useState<string[]>([]);

  const onKindsChange = useCallback((kinds: string[]) => {
    setCanvasKinds(moduleKindsOnly(kinds));
  }, []);

  const onTeamChange = useCallback((next: TeamAssignment[]) => {
    setTeam((prev) => {
      const a = prev.map((row) => `${row.employee_key}:${row.module}`).join("|");
      const b = next.map((row) => `${row.employee_key}:${row.module}`).join("|");
      return a === b ? prev : next;
    });
  }, []);

  const onEmployeeKeysChange = useCallback((keys: string[]) => {
    setEmployeeKeysOnCanvas((prev) => (prev.join(",") === keys.join(",") ? prev : keys));
  }, []);

  const onSelectionChange = useCallback((node: SelectedCanvasNode | null) => {
    setSelected(node);
  }, []);

  const onPlaceKindsApplied = useCallback(() => {
    setPlaceKinds(null);
  }, []);

  const onUnusedPalette = useCallback((kinds: string[]) => {
    setUnusedPalette((prev) => (prev.join(",") === kinds.join(",") ? prev : kinds));
  }, []);

  const unusedEmployees = useMemo(() => {
    const placed = new Set(employeeKeysOnCanvas);
    return employeePalette.filter((item) => !placed.has(item.employee_key));
  }, [employeePalette, employeeKeysOnCanvas]);

  async function readDetail(response: Response): Promise<string> {
    try {
      const body = (await response.json()) as { detail?: string };
      return body.detail || "";
    } catch {
      return "";
    }
  }

  async function saveRule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/backend/api/operator/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          when_event: whenEvent,
          if_threshold: ifThreshold,
          then_action: thenAction,
        }),
      });
      if (!response.ok) {
        setError(ruleError(response.status, await readDetail(response)));
        return;
      }
      setWhenEvent("");
      setIfThreshold("");
      setThenAction("");
      router.refresh();
    } catch {
      setError("No se guardó la regla.");
    } finally {
      setPending(false);
    }
  }

  async function publish(id: string) {
    setPublishingId(id);
    setError("");
    try {
      const response = await fetch(`/api/backend/api/operator/rules/${encodeURIComponent(id)}/publish`, {
        method: "POST",
      });
      if (!response.ok) {
        setError("No se publicó la regla.");
        return;
      }
      router.refresh();
    } catch {
      setError("No se publicó la regla.");
    } finally {
      setPublishingId("");
    }
  }

  async function checkConnection(from: string, to: string, chosenPort: string) {
    setPending(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/backend/api/operator/connections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: from, target: to, port: chosenPort }),
      });
      if (!response.ok) {
        setError(ruleError(response.status, await readDetail(response)));
        return;
      }
      const body = (await response.json()) as FlowEdge;
      setNotice(`${label(body.source)} → ${label(body.target)} · ${body.port}`);
    } catch {
      setError("No se pudo revisar la conexión.");
    } finally {
      setPending(false);
    }
  }

  async function connectModules(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await checkConnection(source, target, port);
  }

  async function publishNext(id: string) {
    setPublishingId(id);
    setError("");
    try {
      const revised = await fetch(`/api/backend/api/operator/rules/${encodeURIComponent(id)}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ then_action: replacement }),
      });
      if (!revised.ok) {
        setError(ruleError(revised.status, await readDetail(revised)));
        return;
      }
      const published = await fetch(`/api/backend/api/operator/rules/${encodeURIComponent(id)}/publish`, {
        method: "POST",
      });
      if (!published.ok) {
        setError("No se publicó la regla.");
        return;
      }
      setReplacement("");
      router.refresh();
    } catch {
      setError("No se publicó la regla.");
    } finally {
      setPublishingId("");
    }
  }

  async function revert(rule: CatalogRule) {
    setPublishingId(rule.id);
    setError("");
    try {
      const response = await fetch(`/api/backend/api/operator/rules/${encodeURIComponent(rule.id)}/revert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: (rule.version ?? 1) - 1 }),
      });
      if (!response.ok) {
        setError("No se restauró la regla.");
        return;
      }
      router.refresh();
    } catch {
      setError("No se restauró la regla.");
    } finally {
      setPublishingId("");
    }
  }

  async function tryMap() {
    setMapBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/backend/api/operator/flow-map/try", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kinds: canvasKinds }),
      });
      if (!response.ok) {
        setError(ruleError(response.status, await readDetail(response)));
        return;
      }
      const body = (await response.json()) as { kinds: string[] };
      setNotice(`Prueba ok · ${body.kinds.map(label).join(" → ")}. Sin publicar.`);
    } catch {
      setError("No se pudo probar el mapa.");
    } finally {
      setMapBusy(false);
    }
  }

  async function publishMap() {
    if (!tenantId) {
      setError("Elegí un negocio antes de publicar el mapa.");
      return;
    }
    setMapBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(
        `/api/backend/api/operator/flow-map/publish?tenant_id=${encodeURIComponent(tenantId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kinds: canvasKinds, team }),
        },
      );
      if (!response.ok) {
        setError(ruleError(response.status, await readDetail(response)));
        return;
      }
      const body = (await response.json()) as { kinds: string[]; team?: TeamAssignment[] };
      const teamNote =
        body.team && body.team.length > 0 ? ` · equipo ${body.team.length}` : "";
      setNotice(`Publicado · ${body.kinds.map(label).join(" → ")}${teamNote}.`);
      router.refresh();
    } catch {
      setError("No se publicó el mapa.");
    } finally {
      setMapBusy(false);
    }
  }

  async function proposeMap() {
    setMapBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/backend/api/operator/flow-map/propose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kinds: canvasKinds }),
      });
      if (!response.ok) {
        setError("El asistente no pudo proponer un mapa.");
        return;
      }
      const body = (await response.json()) as { proposal: string[]; message: string };
      setProposal(body.proposal);
      setNotice(body.message);
    } catch {
      setError("El asistente no pudo proponer un mapa.");
    } finally {
      setMapBusy(false);
    }
  }

  function applyProposal() {
    if (!proposal) return;
    setPlaceKinds(proposal);
    setNotice("Propuesta aplicada en el lienzo. Revisá y después Probá o Publicá.");
    setProposal(null);
  }

  const selectedPorts = selected ? outboundPorts(compatible, selected.kind) : [];
  const coreReady = hasLockedCore(canvasKinds);
  const unusedSet = new Set(unusedPalette);

  return (
    <div className={styles.studio}>
      <header className={styles.topBar}>
        <div className={styles.topMeta}>
          <p className={styles.topEyebrow}>Flujo de ventas</p>
          <h1 className={styles.topTitle}>Equipo digital del negocio</h1>
        </div>
        <div className={styles.topActions} role="group" aria-label="Acciones del mapa">
          <button type="button" disabled={mapBusy} onClick={() => void tryMap()}>
            {mapBusy ? "Probando…" : "Probar"}
          </button>
          <button type="button" disabled={mapBusy} onClick={() => void proposeMap()}>
            Proponer
          </button>
          {proposal ? (
            <button type="button" onClick={applyProposal}>
              Aplicar propuesta
            </button>
          ) : null}
          <button
            type="button"
            className={styles.primary}
            disabled={mapBusy || !coreReady}
            onClick={() => void publishMap()}
          >
            Publicar
          </button>
        </div>
      </header>

      <div className={styles.workspace}>
        <aside className={styles.catalog} aria-label="Catálogo de capacidades">
          <p className={styles.catalogHead}>Capacidades</p>
          <p className={styles.catalogHint}>
            Arrastrá módulos y empleados al centro. Conectá un empleado a un módulo con el puerto
            equipo.
          </p>
          {unusedEmployees.length > 0 ? (
            <div className={styles.category}>
              <p className={styles.categoryTitle}>Equipo</p>
              {unusedEmployees.map((item) => (
                <button
                  key={item.employee_key}
                  type="button"
                  className={styles.paletteItem}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(
                      "application/x-factory-employee",
                      JSON.stringify(item),
                    );
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                >
                  <span className={styles.toneDot} data-tone="channel" aria-hidden="true" />
                  {item.display_name}
                </button>
              ))}
            </div>
          ) : null}
          {unusedPalette.length === 0 ? (
            <p className={styles.paletteEmpty}>Todos los módulos ya están en el mapa.</p>
          ) : (
            CATALOG_GROUPS.map((group) => {
              const items = group.kinds.filter((kind) => unusedSet.has(kind));
              if (items.length === 0) return null;
              return (
                <div key={group.title} className={styles.category}>
                  <p className={styles.categoryTitle}>{group.title}</p>
                  {items.map((item) => (
                    <button
                      key={item}
                      type="button"
                      className={styles.paletteItem}
                      draggable
                      onDragStart={(event) => {
                        event.dataTransfer.setData("application/x-factory-palette", item);
                        event.dataTransfer.effectAllowed = "copy";
                      }}
                    >
                      <span className={styles.toneDot} data-tone={toneFor(item)} aria-hidden="true" />
                      {label(item)}
                    </button>
                  ))}
                </div>
              );
            })
          )}
        </aside>

        <section className={styles.stage} aria-label="Lienzo del negocio">
          <ReactFlowProvider>
            <FlowCanvas
              initialNodes={initialNodes}
              initialEdges={edges}
              positions={initialPositions}
              compatible={compatible}
              palette={palette}
              employeePalette={employeePalette}
              port={port}
              placeKinds={placeKinds}
              onPortMismatch={() => setError(ruleError(400, "port_mismatch"))}
              onConnected={(edge) => {
                if (isEmployeeNodeId(edge.source)) {
                  setNotice(`${edge.source.replace("emp:", "")} → ${label(edge.target)} · equipo`);
                  return;
                }
                void checkConnection(edge.source, edge.target, edge.port);
              }}
              onPlaced={(kind) => {
                setNotice(`${label(kind)} sumado al mapa.`);
                setError("");
              }}
              onSelectionChange={onSelectionChange}
              onKindsChange={onKindsChange}
              onTeamChange={onTeamChange}
              onEmployeeKeysChange={onEmployeeKeysChange}
              onPlaceKindsApplied={onPlaceKindsApplied}
              onUnusedPalette={onUnusedPalette}
            />
          </ReactFlowProvider>
        </section>

        <aside className={styles.inspector} aria-label="Inspector">
          <h2>Capacidad</h2>
          <FlowPropertiesPanel selected={selected} ports={selectedPorts} />
          {proposal ? (
            <div className={styles.properties}>
              <p className="meta">Propuesta (sin publicar)</p>
              <p>{proposal.map(label).join(" → ")}</p>
            </div>
          ) : null}

          <h2>Conexión</h2>
          <form onSubmit={connectModules}>
            <label htmlFor="flow-source">Desde</label>
            <select id="flow-source" value={source} onChange={(event) => setSource(event.target.value)}>
              {ORDER.map((id) => (
                <option key={id} value={id}>
                  {label(id)}
                </option>
              ))}
            </select>
            <label htmlFor="flow-port">Puerto</label>
            <select id="flow-port" value={port} onChange={(event) => setPort(event.target.value)}>
              <option value="pedido">pedido</option>
              <option value="pago_confirmado">pago_confirmado</option>
              <option value="aviso">aviso</option>
              <option value="aprobacion">aprobacion</option>
            </select>
            <label htmlFor="flow-target">Hacia</label>
            <select id="flow-target" value={target} onChange={(event) => setTarget(event.target.value)}>
              {ORDER.map((id) => (
                <option key={id} value={id}>
                  {label(id)}
                </option>
              ))}
            </select>
            <button type="submit" disabled={pending}>
              {pending ? "Revisando…" : "Revisar conexión"}
            </button>
          </form>

          <h2>Camino fijo</h2>
          <ul className={styles.edges}>
            {edges.map((edge) => (
              <li key={`${edge.source}-${edge.target}-${edge.port}`}>
                <span>
                  {label(edge.source)} → {label(edge.target)}
                </span>
                {edge.locked ? <span className={styles.lock}>Fijo</span> : null}
              </li>
            ))}
          </ul>

          <h2>Reglas</h2>
          <form onSubmit={saveRule}>
            <label htmlFor="rule-when">Cuando</label>
            <input
              id="rule-when"
              value={whenEvent}
              onChange={(event) => setWhenEvent(event.target.value)}
              required
            />
            <label htmlFor="rule-if">Si</label>
            <input
              id="rule-if"
              value={ifThreshold}
              onChange={(event) => setIfThreshold(event.target.value)}
              required
            />
            <label htmlFor="rule-then">Entonces</label>
            <input
              id="rule-then"
              value={thenAction}
              onChange={(event) => setThenAction(event.target.value)}
              required
            />
            <button type="submit" disabled={pending}>
              {pending ? "Guardando…" : "Guardar borrador"}
            </button>
          </form>
          <label htmlFor="rule-next">Próxima versión</label>
          <input
            id="rule-next"
            value={replacement}
            onChange={(event) => setReplacement(event.target.value)}
            placeholder="Nuevo Entonces"
          />
          {rules.length === 0 ? (
            <p className="meta">Sin reglas extra. El camino fijo sigue corriendo.</p>
          ) : null}
          <ul className={styles.rules}>
            {rules.map((rule) => (
              <li key={rule.id} className={styles.rule}>
                <p>
                  Cuando {rule.when_event}. Si {rule.if_threshold}. Entonces {rule.then_action}.
                </p>
                <p className="meta">
                  {rule.status === "published" ? "Publicada" : "Borrador"}
                  {rule.version ? ` · v${rule.version}` : ""}
                </p>
                {rule.status === "draft" ? (
                  <button
                    type="button"
                    disabled={publishingId === rule.id}
                    onClick={() => publish(rule.id)}
                  >
                    {publishingId === rule.id ? "Publicando…" : "Publicar regla"}
                  </button>
                ) : null}
                {rule.status === "published" ? (
                  <button
                    type="button"
                    disabled={publishingId === rule.id || replacement.trim() === ""}
                    onClick={() => publishNext(rule.id)}
                  >
                    Publicar siguiente
                  </button>
                ) : null}
                {(rule.version ?? 1) > 1 ? (
                  <button
                    type="button"
                    disabled={publishingId === rule.id}
                    onClick={() => revert(rule)}
                  >
                    Revertir
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <footer className={styles.bottomBar}>
        <div className={styles.bottomStatus}>
          <span className={`${styles.pill} ${published ? styles.pillOk : styles.pillWarn}`}>
            {published ? "Publicado" : "Borrador"}
          </span>
          <span>
            {published
              ? (publishedKinds ?? []).map(label).join(" → ") || "Mapa activo"
              : "El turno sigue los módulos activos hasta publicar"}
          </span>
          {!coreReady ? (
            <span className={`${styles.pill} ${styles.pillWarn}`}>Faltan Pedido y Cobros</span>
          ) : null}
        </div>
        {notice ? <p className={styles.bottomMsg}>{notice}</p> : null}
        {error ? <p className={styles.bottomErr}>{error}</p> : null}
      </footer>
    </div>
  );
}
