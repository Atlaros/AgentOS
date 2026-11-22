"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { DirectoryForm, type SupplierRow } from "./directory-form";
import styles from "./suppliers.module.css";

type CatalogItem = {
  variant_sku: string;
  name: string;
  codigo?: string;
  stock: number;
  supplier_id?: string | null;
  reorder_threshold?: number;
};

export function DirectoryPanel({
  suppliers,
  variants,
}: {
  suppliers: SupplierRow[];
  variants: CatalogItem[];
}) {
  const router = useRouter();
  const [editing, setEditing] = useState<SupplierRow | null>(null);
  const [busyId, setBusyId] = useState("");
  const [assignError, setAssignError] = useState("");
  const [assignBusy, setAssignBusy] = useState(false);

  const activeSuppliers = useMemo(
    () => suppliers.filter((item) => item.active),
    [suppliers],
  );
  const unassigned = useMemo(
    () => variants.filter((item) => !item.supplier_id).slice(0, 40),
    [variants],
  );

  async function deactivate(supplier: SupplierRow) {
    setBusyId(supplier.id);
    try {
      const res = await fetch(`/api/backend/api/suppliers/${encodeURIComponent(supplier.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: false }),
      });
      if (!res.ok) throw new Error(String(res.status));
      if (editing?.id === supplier.id) setEditing(null);
      router.refresh();
    } finally {
      setBusyId("");
    }
  }

  async function onAssign(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const variantSku = String(data.get("variant_sku") || "").trim();
    const supplierId = String(data.get("supplier_id") || "").trim();
    const threshold = Number(data.get("threshold") || 1);
    if (!variantSku || !supplierId) {
      setAssignError("Elegí variante y proveedor.");
      return;
    }
    if (!Number.isInteger(threshold) || threshold < 0) {
      setAssignError("El umbral debe ser un entero ≥ 0.");
      return;
    }
    setAssignBusy(true);
    setAssignError("");
    try {
      const link = await fetch(
        `/api/backend/api/catalog/variants/${encodeURIComponent(variantSku)}/supplier`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ supplier_id: supplierId }),
        },
      );
      if (!link.ok) throw new Error(String(link.status));
      const thr = await fetch(
        `/api/backend/api/catalog/variants/${encodeURIComponent(variantSku)}/reorder-threshold`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ threshold }),
        },
      );
      if (!thr.ok) throw new Error(String(thr.status));
      event.currentTarget.reset();
      router.refresh();
    } catch (err) {
      setAssignError(err instanceof Error ? err.message : "error");
    } finally {
      setAssignBusy(false);
    }
  }

  return (
    <>
      <DirectoryForm
        key={editing?.id || "new"}
        initial={editing}
        onDone={() => setEditing(null)}
      />

      <div className={styles.panel}>
        <h3 className={styles.panelTitle}>Asignar productos</h3>
        <p className={styles.panelLead}>
          Vinculá una variante al proveedor preferido y definí el umbral de reposición.
        </p>
        <form onSubmit={onAssign}>
          <div className={styles.assignRow}>
            <label>
              Variante
              <select name="variant_sku" defaultValue="" required>
                <option value="" disabled>
                  Elegir…
                </option>
                {unassigned.map((item) => (
                  <option key={item.variant_sku} value={item.variant_sku}>
                    {(item.codigo || item.variant_sku) + " · " + item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Proveedor
              <select name="supplier_id" defaultValue="" required>
                <option value="" disabled>
                  Elegir…
                </option>
                {activeSuppliers.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Umbral
              <input name="threshold" type="number" min={0} defaultValue={1} required />
            </label>
          </div>
          <button type="submit" disabled={assignBusy || activeSuppliers.length === 0}>
            {assignBusy ? "…" : "Asignar"}
          </button>
          {assignError ? <p className="error">{assignError}</p> : null}
          {unassigned.length === 0 ? (
            <p className={styles.muted}>No hay variantes sin proveedor en esta muestra.</p>
          ) : null}
        </form>
      </div>

      <h2 className="section-title">Proveedores ({suppliers.length})</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Contacto</th>
              <th>WhatsApp</th>
              <th>Pago</th>
              <th>Plazo</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {suppliers.length === 0 ? (
              <tr>
                <td colSpan={7}>Todavía no hay proveedores en el directorio.</td>
              </tr>
            ) : (
              suppliers.map((item) => (
                <tr key={item.id}>
                  <td>{item.name}</td>
                  <td>{item.contact_name || "—"}</td>
                  <td>{item.whatsapp || item.phone || "—"}</td>
                  <td>{item.payment_terms === "credit" ? "Crédito" : "Contado"}</td>
                  <td>{item.lead_time_days} d</td>
                  <td>{item.active ? "Activo" : "Inactivo"}</td>
                  <td>
                    <div className={styles.actions}>
                      <button type="button" onClick={() => setEditing(item)}>
                        Editar
                      </button>
                      {item.active ? (
                        <button
                          type="button"
                          disabled={busyId === item.id}
                          onClick={() => void deactivate(item)}
                        >
                          {busyId === item.id ? "…" : "Desactivar"}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
