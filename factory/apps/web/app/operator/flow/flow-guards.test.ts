import { describe, expect, it } from "vitest";
import {
  canAssignEmployee,
  canConnect,
  hasLockedCore,
  isCanvasItemDeletable,
  isEmployeeNodeId,
  moduleKindsOnly,
  outboundPorts,
  proposeCanvasKinds,
  teamFromEdges,
} from "./flow-guards";

const compatible = {
  cobros: { pago_confirmado: ["caja"] },
  pedido: { pedido: ["cobros"] },
  whatsapp: { aviso: ["aprobacion"] },
};

describe("canConnect", () => {
  it("allows a server-compatible port link", () => {
    expect(canConnect(compatible, "pago_confirmado", "cobros", "caja")).toBe(true);
  });

  it("rejects a link on a mismatched port", () => {
    expect(canConnect(compatible, "pago_confirmado", "cobros", "contabilidad")).toBe(false);
    expect(canConnect(compatible, "pedido", "cobros", "caja")).toBe(false);
  });

  it("rejects self-links and missing endpoints", () => {
    expect(canConnect(compatible, "pago_confirmado", "cobros", "cobros")).toBe(false);
    expect(canConnect(compatible, "pago_confirmado", null, "caja")).toBe(false);
    expect(canConnect(compatible, "pago_confirmado", "cobros", undefined)).toBe(false);
  });
});

describe("isCanvasItemDeletable", () => {
  it("keeps locked core nodes and edges on the canvas", () => {
    expect(isCanvasItemDeletable(true)).toBe(false);
  });

  it("allows deleting unlocked items", () => {
    expect(isCanvasItemDeletable(false)).toBe(true);
  });
});

describe("hasLockedCore", () => {
  it("requires pedido and cobros together", () => {
    expect(hasLockedCore(["whatsapp", "pedido"])).toBe(false);
    expect(hasLockedCore(["pedido", "cobros"])).toBe(true);
  });
});

describe("outboundPorts", () => {
  it("lists ports the selected kind can emit", () => {
    expect(outboundPorts(compatible, "cobros")).toEqual(["pago_confirmado"]);
    expect(outboundPorts(compatible, "missing")).toEqual([]);
  });
});

describe("proposeCanvasKinds", () => {
  it("fills locked core and unused palette without publishing", () => {
    expect(proposeCanvasKinds(["whatsapp"], ["whatsapp", "pedido", "cobros", "caja"])).toEqual([
      "whatsapp",
      "pedido",
      "cobros",
      "caja",
    ]);
  });

  it("keeps existing kinds when the core is already present", () => {
    expect(proposeCanvasKinds(["pedido", "cobros"], ["pedido", "cobros", "caja"])).toEqual([
      "pedido",
      "cobros",
      "caja",
    ]);
  });
});

describe("employee canvas helpers", () => {
  it("strips employee tokens from module kinds", () => {
    expect(moduleKindsOnly(["whatsapp", "emp:sales", "employee", "cobros"])).toEqual([
      "whatsapp",
      "cobros",
    ]);
  });

  it("builds team assignments from equipo edges", () => {
    expect(
      teamFromEdges([
        { source: "emp:sales", target: "whatsapp", port: "equipo" },
        { source: "pedido", target: "cobros", port: "pedido" },
      ]),
    ).toEqual([{ employee_key: "sales", module: "whatsapp" }]);
    expect(isEmployeeNodeId("emp:sales")).toBe(true);
    expect(canAssignEmployee(["whatsapp", "pedido"], "whatsapp")).toBe(true);
    expect(canAssignEmployee(["whatsapp"], "cobros")).toBe(false);
  });
});
