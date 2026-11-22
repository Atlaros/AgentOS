"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { formatCashWhen, mapCashError, readCashDetail } from "./cash-form";
import styles from "./cash.module.css";
import { MovementDetail } from "./movement-detail";

/** Legacy cash-only row shape (still returned by GET /api/cash movements). */
export type CashMovement = {
  id: string;
  direction: string;
  amount: string;
  currency: string;
  reason: string;
  category?: string;
  method?: string;
  status?: string;
  recorded_by_name?: string;
  created_at?: string | null;
  ticket_id?: string | null;
  void_reason?: string | null;
  voided_by_name?: string | null;
  voided_at?: string | null;
};

/** Unified session activity entry (cash movement or informative QR sale). */
export type CashActivityEntry = {
  id: string;
  kind: "cash_movement" | "qr_sale" | string;
  created_at?: string | null;
  direction?: string | null;
  amount: string;
  currency: string;
  category?: string;
  method?: string;
  status?: string;
  affects_cash?: boolean;
  reason?: string;
  summary?: string;
  recorded_by_name?: string;
  ticket_id?: string | null;
  ticket_number?: string | null;
  session_id?: string | null;
  movement_id?: string | null;
  void_reason?: string | null;
};

const DIRECTION_LABEL: Record<string, string> = {
  in: "Entrada",
  out: "Salida",
};

const STATUS_LABEL: Record<string, string> = {
  recorded: "Vigente",
  voided: "Anulado",
  pending_qr: "Pendiente QR",
};

const METHOD_LABEL: Record<string, string> = {
  cash: "Efectivo",
  qr: "QR",
};

function ticketLabel(entry: CashActivityEntry): string {
  if (entry.ticket_number) return entry.ticket_number;
  const match = (entry.reason || "").match(/\bTK-[A-Za-z0-9-]+\b/);
  if (match) return match[0];
  if (entry.ticket_id) return "Ticket";
  return "—";
}

function methodBadge(entry: CashActivityEntry) {
  const method = (entry.method || "cash").toLowerCase();
  const label = METHOD_LABEL[method] || method;
  const informative = entry.affects_cash === false;
  return (
    <span className={informative ? styles.methodBadgeQr : styles.methodBadge}>
      {label}
      {informative ? (
        <span className={styles.methodHint}> · no afecta efectivo</span>
      ) : null}
    </span>
  );
}

export function MovementsTable({
  entries,
  count,
}: {
  entries: CashActivityEntry[];
  count?: number;
}) {
  const router = useRouter();
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<CashActivityEntry | null>(null);
  const [attachmentCounts, setAttachmentCounts] = useState<Record<string, number>>({});
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const shown = typeof count === "number" ? count : entries.length;

  useEffect(() => {
    let cancelled = false;
    async function loadCounts() {
      const next: Record<string, number> = {};
      const cashRows = entries.filter(
        (entry) => entry.kind === "cash_movement" && entry.affects_cash !== false,
      );
      await Promise.all(
        cashRows.map(async (entry) => {
          const movementId = entry.movement_id || entry.id;
          try {
            const res = await fetch(
              `/api/backend/api/cash/${encodeURIComponent(movementId)}/attachments`,
            );
            if (!res.ok) return;
            const data = (await res.json()) as { attachments?: unknown[] };
            next[movementId] = Array.isArray(data.attachments) ? data.attachments.length : 0;
          } catch {
            // Ignore transient count failures; table still works.
          }
        }),
      );
      if (!cancelled) setAttachmentCounts(next);
    }
    void loadCounts();
    return () => {
      cancelled = true;
    };
  }, [entries]);

  async function voidMovement(entry: CashActivityEntry) {
    const movementId = entry.movement_id || entry.id;
    const reason = window.prompt("Motivo de anulación") ?? "";
    if (!reason.trim()) {
      setError(mapCashError("void_reason_required", "Indicá el motivo de la anulación."));
      return;
    }
    const pinRaw = window.prompt("PIN (si corresponde; dejá vacío si no aplica)");
    if (pinRaw === null) return;
    setBusyId(movementId);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/cash/${encodeURIComponent(movementId)}/void`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: reason.trim(),
          pin: pinRaw.trim() || null,
        }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo anular el movimiento."));
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudo anular el movimiento.");
    } finally {
      setBusyId("");
    }
  }

  async function uploadAttachment(entry: CashActivityEntry, file: File) {
    const movementId = entry.movement_id || entry.id;
    setBusyId(movementId);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(
        `/api/backend/api/cash/${encodeURIComponent(movementId)}/attachments`,
        {
          method: "POST",
          body: form,
        },
      );
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo adjuntar el archivo."));
        return;
      }
      router.refresh();
    } catch {
      setError("No se pudo adjuntar el archivo.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section aria-labelledby="cash-movements-title">
      <h2 id="cash-movements-title" className={styles.sectionTitle}>
        Movimientos del turno
        <span className="meta"> · {shown}</span>
      </h2>
      {error ? <p className="error">{error}</p> : null}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Tipo</th>
              <th>Categoría</th>
              <th>Método</th>
              <th>Monto</th>
              <th>Resumen</th>
              <th>Estado</th>
              <th>Ticket</th>
              <th>Adjuntos</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 ? (
              <tr>
                <td colSpan={11}>Todavía no hay movimientos en este turno.</td>
              </tr>
            ) : (
              entries.map((entry) => {
                const voided = entry.status === "voided";
                const isCash = entry.kind === "cash_movement" && entry.affects_cash !== false;
                const movementId = entry.movement_id || entry.id;
                const attachCount = isCash ? (attachmentCounts[movementId] ?? 0) : 0;
                const summary = entry.summary || entry.reason || "—";
                const selectedRow = selected?.id === entry.id && selected?.kind === entry.kind;
                return (
                  <tr
                    key={`${entry.kind}-${entry.id}`}
                    className={[
                      voided ? styles.voidedRow : "",
                      styles.clickableRow,
                      selectedRow ? styles.selectedRow : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    tabIndex={0}
                    onClick={() => setSelected(entry)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(entry);
                      }
                    }}
                  >
                    <td className={styles.num}>{formatCashWhen(entry.created_at)}</td>
                    <td>{entry.recorded_by_name || "—"}</td>
                    <td>
                      {entry.direction
                        ? DIRECTION_LABEL[entry.direction] || entry.direction
                        : entry.affects_cash === false
                          ? "QR"
                          : "—"}
                    </td>
                    <td>{entry.category || "—"}</td>
                    <td>{methodBadge(entry)}</td>
                    <td className={styles.num}>
                      {entry.amount} {entry.currency}
                    </td>
                    <td className={styles.summaryCell}>
                      {summary}
                      {voided && entry.void_reason ? (
                        <span className="meta"> · anulado: {entry.void_reason}</span>
                      ) : null}
                    </td>
                    <td>{STATUS_LABEL[entry.status || ""] || entry.status || "—"}</td>
                    <td>{ticketLabel(entry)}</td>
                    <td className={styles.num}>
                      {isCash && attachCount > 0 ? `${attachCount}` : isCash ? "—" : "—"}
                    </td>
                    <td className={styles.voidCell}>
                      <div className={styles.rowActions}>
                        {isCash && !voided ? (
                          <>
                            <input
                              ref={(node) => {
                                fileInputRefs.current[movementId] = node;
                              }}
                              type="file"
                              className={styles.hiddenFile}
                              aria-label={`Adjuntar archivo a movimiento ${movementId}`}
                              onClick={(event) => event.stopPropagation()}
                              onChange={(event) => {
                                const file = event.target.files?.[0];
                                event.target.value = "";
                                if (file) void uploadAttachment(entry, file);
                              }}
                            />
                            <button
                              type="button"
                              className="secondary"
                              disabled={Boolean(busyId)}
                              onClick={(event) => {
                                event.stopPropagation();
                                fileInputRefs.current[movementId]?.click();
                              }}
                              aria-label="Adjuntar comprobante"
                            >
                              {busyId === movementId ? "…" : "Adjuntar"}
                            </button>
                            <button
                              type="button"
                              className="secondary"
                              disabled={Boolean(busyId)}
                              onClick={(event) => {
                                event.stopPropagation();
                                void voidMovement(entry);
                              }}
                              aria-label="Anular movimiento"
                            >
                              {busyId === movementId ? "…" : "Anular"}
                            </button>
                          </>
                        ) : (
                          "—"
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <MovementDetail entry={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
