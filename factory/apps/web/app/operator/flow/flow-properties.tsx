"use client";

import type { SelectedCanvasNode } from "./flow-guards";
import styles from "./flow-board.module.css";

export function FlowPropertiesPanel({
  selected,
  ports,
}: {
  selected: SelectedCanvasNode | null;
  ports: string[];
}) {
  if (!selected) {
    return <p className="meta">Elegí un nodo en el lienzo para verlo. Sin código.</p>;
  }
  return (
    <div className={styles.properties} data-testid="flow-properties">
      <p>
        <strong>{selected.label}</strong>
      </p>
      <p className="meta">Tipo · {selected.kind}</p>
      <p className="meta">{selected.locked ? "Nodo del núcleo (fijo)" : "Módulo opcional"}</p>
      <p className="meta">
        Puertos de salida · {ports.length > 0 ? ports.join(", ") : "ninguno"}
      </p>
    </div>
  );
}
