"use client";

import { useRouter } from "next/navigation";

import styles from "./cash.module.css";
import type { CashSession } from "./session-panel";

export type CashFilterValues = {
  direction: string;
  category: string;
  method: string;
  status: string;
  user: string;
  from: string;
  to: string;
  session_id: string;
};

function buildMovementsHref(filters: Record<string, string>): string {
  const params = new URLSearchParams();
  params.set("tab", "movements");
  for (const [key, value] of Object.entries(filters)) {
    const trimmed = value.trim();
    if (trimmed) params.set(key, trimmed);
  }
  return `/cash?${params.toString()}`;
}

function exportHref(format: "csv" | "pdf", filters: CashFilterValues): string {
  const params = new URLSearchParams();
  params.set("format", format);
  for (const [key, value] of Object.entries(filters)) {
    if (key === "session_id") continue;
    const trimmed = value.trim();
    if (trimmed) params.set(key, trimmed);
  }
  return `/api/backend/api/cash/export?${params.toString()}`;
}

function sessionOptionLabel(session: CashSession): string {
  const when = session.closed_at || session.opened_at || "";
  const stamp = when ? when.slice(0, 16).replace("T", " ") : session.id.slice(0, 8);
  const state = session.status === "open" ? "Abierto" : "Cerrado";
  return `${state} · ${stamp}`;
}

export function CashFilters({
  filters,
  sessions,
}: {
  filters: CashFilterValues;
  sessions: CashSession[];
}) {
  const router = useRouter();

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const next: CashFilterValues = {
      direction: String(data.get("direction") || ""),
      category: String(data.get("category") || ""),
      method: String(data.get("method") || ""),
      status: String(data.get("status") || ""),
      user: String(data.get("user") || ""),
      from: String(data.get("from") || ""),
      to: String(data.get("to") || ""),
      session_id: String(data.get("session_id") || ""),
    };
    router.push(buildMovementsHref(next));
  }

  function onReset() {
    router.push("/cash?tab=movements");
  }

  return (
    <section className={styles.panel} aria-labelledby="cash-filters-title">
      <h2 id="cash-filters-title" className={styles.panelTitle}>
        Filtros y export
      </h2>
      <p className={styles.panelLead}>
        Filtrá el feed de Movimientos del turno. El QR aparece como informativo y no
        mueve el efectivo. El arqueo del turno no cambia con estos filtros.
      </p>
      <form className={styles.filtersForm} onSubmit={onSubmit}>
        <label>
          Turno
          <select name="session_id" defaultValue={filters.session_id}>
            <option value="">Turno actual / último</option>
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {sessionOptionLabel(session)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tipo
          <select name="direction" defaultValue={filters.direction}>
            <option value="">Todos</option>
            <option value="in">Entrada</option>
            <option value="out">Salida</option>
          </select>
        </label>
        <label>
          Método
          <select name="method" defaultValue={filters.method}>
            <option value="">Todos</option>
            <option value="cash">Efectivo</option>
            <option value="qr">QR</option>
          </select>
        </label>
        <label>
          Categoría
          <input
            name="category"
            type="text"
            defaultValue={filters.category}
            placeholder="venta, envio…"
            autoComplete="off"
          />
        </label>
        <label>
          Estado
          <select name="status" defaultValue={filters.status}>
            <option value="">Todos</option>
            <option value="recorded">Vigente</option>
            <option value="pending_qr">Pendiente QR</option>
            <option value="voided">Anulado</option>
          </select>
        </label>
        <label>
          Usuario
          <input
            name="user"
            type="text"
            defaultValue={filters.user}
            placeholder="nombre"
            autoComplete="off"
          />
        </label>
        <label>
          Desde
          <input name="from" type="date" defaultValue={filters.from} />
        </label>
        <label>
          Hasta
          <input name="to" type="date" defaultValue={filters.to} />
        </label>
        <div className={styles.filterActions}>
          <button type="submit">Aplicar</button>
          <button type="button" className="secondary" onClick={onReset}>
            Limpiar
          </button>
        </div>
      </form>
      <div className={styles.exportRow}>
        <a
          className={styles.exportLink}
          href={exportHref("csv", filters)}
          target="_blank"
          rel="noreferrer"
        >
          Exportar CSV
        </a>
        <a
          className={styles.exportLink}
          href={exportHref("pdf", filters)}
          target="_blank"
          rel="noreferrer"
        >
          Exportar PDF
        </a>
      </div>
    </section>
  );
}
