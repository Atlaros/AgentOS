"use client";

import { useCallback, useEffect, useState } from "react";

import styles from "./operator.module.css";

type BusinessOption = {
  tenant_id: string;
  name: string;
};

type EmployeeRow = {
  employee_key: string;
  base_role: string;
  display_name: string;
  style: string;
  enabled: boolean;
  is_clone: boolean;
  archived: boolean;
  locked: boolean;
};

type EmployeesPanelProps = {
  businesses: BusinessOption[];
};

const BASE_ROLE_OPTIONS = [
  { value: "sales", label: "Ventas (Adri)" },
  { value: "collections", label: "Cobros" },
  { value: "ops", label: "Operaciones" },
  { value: "postventa", label: "Postventa" },
  { value: "inventory", label: "Inventario" },
  { value: "catalog_admin", label: "Catálogo" },
  { value: "accounting", label: "Contabilidad" },
  { value: "analyst", label: "Analista" },
  { value: "suppliers", label: "Proveedores" },
];

const ROLE_LABELS: Record<string, string> = Object.fromEntries(
  BASE_ROLE_OPTIONS.map((option) => [option.value, option.label]),
);

function roleLabel(baseRole: string): string {
  return ROLE_LABELS[baseRole] ?? baseRole;
}

export function EmployeesPanel({ businesses }: EmployeesPanelProps) {
  const [tenantId, setTenantId] = useState(businesses[0]?.tenant_id || "");
  const [rows, setRows] = useState<EmployeeRow[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cloneRole, setCloneRole] = useState("sales");
  const [cloneName, setCloneName] = useState("");
  const [cloneStyle, setCloneStyle] = useState("");

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/backend/api/operator/employees?tenant_id=${encodeURIComponent(id)}`,
        { cache: "no-store" },
      );
      const body = (await response.json()) as {
        detail?: string;
        employees?: EmployeeRow[];
      };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo cargar los empleados.");
      }
      setRows(body.employees || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo cargar los empleados.");
      setRows([]);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(tenantId);
  }, [tenantId, load]);

  if (businesses.length === 0) {
    return null;
  }

  async function patchEmployee(
    employeeKey: string,
    patch: { enabled?: boolean; display_name?: string; style?: string },
  ) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/backend/api/operator/employees", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, employee_key: employeeKey, ...patch }),
        cache: "no-store",
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo actualizar el empleado.");
      }
      setMessage("Empleado actualizado.");
      await load(tenantId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo actualizar el empleado.");
    } finally {
      setBusy(false);
    }
  }

  async function createClone(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/backend/api/operator/employees", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          base_role: cloneRole,
          display_name: cloneName,
          style: cloneStyle,
        }),
        cache: "no-store",
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo crear el empleado.");
      }
      setCloneName("");
      setCloneStyle("");
      setMessage("Empleado propio creado.");
      await load(tenantId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo crear el empleado.");
    } finally {
      setBusy(false);
    }
  }

  async function archiveClone(employeeKey: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await fetch("/api/backend/api/operator/employees", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, employee_key: employeeKey }),
        cache: "no-store",
      });
      const body = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(body.detail || "No se pudo archivar el empleado.");
      }
      setMessage("Empleado archivado.");
      await load(tenantId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No se pudo archivar el empleado.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.employees} aria-labelledby="operator-employees-title">
      <header className={styles.employeesHeader}>
        <div>
          <h2 id="operator-employees-title" className={styles.employeesTitle}>
            Equipo digital
          </h2>
          <p className={styles.employeesLead}>
            Acá activás quién atiende, le ponés nombre y una pista de tono. Los permisos y las
            herramientas vienen del rol base; la autonomía se ajusta en la pestaña Autonomía. Ventas
            y Cobros del catálogo no se apagan.
          </p>
        </div>
        <div className={styles.employeesBusiness}>
          <label htmlFor="employees-business">Negocio</label>
          <select
            id="employees-business"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          >
            {businesses.map((row) => (
              <option key={row.tenant_id} value={row.tenant_id}>
                {row.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {message ? <p className="meta">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <ul className={styles.employeeList}>
        {rows.map((row) => (
          <li key={row.employee_key} className={styles.employeeCard}>
            <div className={styles.employeeCardTop}>
              <div>
                <strong>{row.display_name || roleLabel(row.base_role)}</strong>
                <p className={styles.employeeMeta}>
                  {roleLabel(row.base_role)} · {row.is_clone ? "Copia propia" : "Catálogo"}
                  {row.locked ? " · No se puede apagar" : ""}
                </p>
              </div>
              <label className={styles.employeeToggle}>
                <input
                  type="checkbox"
                  aria-label={`Activo ${row.display_name || row.employee_key}`}
                  checked={row.enabled}
                  disabled={busy || row.locked}
                  onChange={(event) => {
                    void patchEmployee(row.employee_key, { enabled: event.target.checked });
                  }}
                />
                <span>{row.locked ? "Siempre activo" : row.enabled ? "Activo" : "Apagado"}</span>
              </label>
            </div>

            <div className={styles.employeeFields}>
              <label>
                Nombre visible
                <input
                  aria-label={`Nombre de ${row.employee_key}`}
                  defaultValue={row.display_name}
                  disabled={busy}
                  onBlur={(event) => {
                    const next = event.target.value.trim();
                    if (next && next !== row.display_name) {
                      void patchEmployee(row.employee_key, { display_name: next });
                    }
                  }}
                />
              </label>
              <label>
                Tono / personalidad
                <input
                  aria-label={`Estilo de ${row.employee_key}`}
                  defaultValue={row.style}
                  disabled={busy}
                  placeholder="Ej. cálida, breve, de cafetería"
                  onBlur={(event) => {
                    const next = event.target.value.trim();
                    if (next !== row.style) {
                      void patchEmployee(row.employee_key, { style: next });
                    }
                  }}
                />
              </label>
            </div>

            {row.locked ? (
              <p className={styles.employeeNote}>
                Ventas y Cobros del catálogo quedan siempre activos: son el piso comercial del
                negocio.
              </p>
            ) : null}

            {row.is_clone ? (
              <div className={styles.employeeActions}>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy}
                  onClick={() => void archiveClone(row.employee_key)}
                >
                  Archivar copia
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {rows.length === 0 && !busy ? (
        <div className={styles.emptyBox}>
          <p>No hay empleados cargados para este negocio.</p>
        </div>
      ) : null}

      <form className={styles.employeeCreate} onSubmit={createClone}>
        <div className={styles.employeeCreateHead}>
          <h3>Crear copia de un rol</h3>
          <p>
            Hereda las herramientas del rol base. Acá solo elegís nombre y tono — no se agregan
            permisos nuevos ni tools libres.
          </p>
        </div>
        <div className={styles.employeeCreateGrid}>
          <label htmlFor="clone-base-role">
            Rol base
            <select
              id="clone-base-role"
              value={cloneRole}
              onChange={(event) => setCloneRole(event.target.value)}
            >
              {BASE_ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="clone-name">
            Nombre para mostrar
            <input
              id="clone-name"
              value={cloneName}
              onChange={(event) => setCloneName(event.target.value)}
              required
              placeholder="Ej. Adri de la mañana"
            />
          </label>
          <label htmlFor="clone-style" className={styles.employeeCreateWide}>
            Tono / personalidad
            <input
              id="clone-style"
              value={cloneStyle}
              onChange={(event) => setCloneStyle(event.target.value)}
              placeholder="Ej. formal, corta, con humor suave"
            />
          </label>
        </div>
        <button type="submit" disabled={busy || !cloneName.trim()}>
          {busy ? "Guardando…" : "Crear empleado"}
        </button>
      </form>
    </section>
  );
}
