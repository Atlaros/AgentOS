/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FlowPropertiesPanel } from "./flow-properties";

afterEach(() => {
  cleanup();
});

describe("FlowPropertiesPanel", () => {
  it("prompts to select a node when nothing is selected", () => {
    render(<FlowPropertiesPanel selected={null} ports={[]} />);
    expect(screen.getByText(/Elegí un nodo en el lienzo/i)).toBeTruthy();
  });

  it("shows kind, lock state, and outbound ports for the selection", () => {
    render(
      <FlowPropertiesPanel
        selected={{ id: "cobros", kind: "cobros", locked: true, label: "Cobros" }}
        ports={["pago_confirmado"]}
      />,
    );
    expect(screen.getByTestId("flow-properties")).toBeTruthy();
    expect(screen.getByText("Cobros")).toBeTruthy();
    expect(screen.getByText(/Tipo · cobros/)).toBeTruthy();
    expect(screen.getByText(/Nodo del núcleo \(fijo\)/)).toBeTruthy();
    expect(screen.getByText(/Puertos de salida · pago_confirmado/)).toBeTruthy();
  });
});
