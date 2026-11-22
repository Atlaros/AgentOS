"use client";

import { useEffect, useId, useState } from "react";

import { formatCashWhen, mapCashError, readCashDetail } from "./cash-form";
import styles from "./cash.module.css";
import type { CashActivityEntry } from "./movements-table";

export type ActivityLine = {
  name: string;
  variant_sku: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  currency: string;
  talla?: string;
  color?: string;
};

export type ActivityAttachment = {
  id: string;
  filename?: string;
  content_type?: string;
  size_bytes?: number;
  created_at?: string | null;
};

export type ActivityDetail = {
  id: string;
  kind: string;
  status?: string;
  method?: string;
  affects_cash?: boolean;
  direction?: string | null;
  amount: string;
  currency: string;
  category?: string;
  reason?: string;
  summary?: string;
  created_at?: string | null;
  recorded_by_name?: string;
  session_id?: string | null;
  ticket_id?: string | null;
  ticket_number?: string | null;
  movement_id?: string | null;
  lines?: ActivityLine[];
  void_reason?: string | null;
  voided_by_name?: string | null;
  voided_at?: string | null;
  attachments_count?: number;
  attachments?: ActivityAttachment[];
  attachments_href?: string | null;
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

type MovementDetailProps = {
  entry: CashActivityEntry | null;
  onClose: () => void;
};

export function MovementDetail({ entry, onClose }: MovementDetailProps) {
  const titleId = useId();
  const [detail, setDetail] = useState<ActivityDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!entry) {
      setDetail(null);
      setError("");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      setDetail(null);
      const kind =
        entry!.kind === "qr_sale"
          ? "qr_sale"
          : "cash_movement";
      try {
        const res = await fetch(
          `/api/backend/api/cash/activity/${encodeURIComponent(entry!.id)}?kind=${kind}`,
        );
        if (!res.ok) {
          const detailCode = await readCashDetail(res);
          if (!cancelled) {
            setError(mapCashError(detailCode, "No se pudo cargar el detalle."));
          }
          return;
        }
        const body = (await res.json()) as ActivityDetail;
        if (!cancelled) setDetail(body);
      } catch {
        if (!cancelled) setError("No se pudo cargar el detalle.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [entry]);

  useEffect(() => {
    if (!entry) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [entry, onClose]);

  if (!entry) return null;

  const method = (detail?.method || entry.method || "cash").toLowerCase();
  const lines = detail?.lines || [];
  const attachments = detail?.attachments || [];
  const ticketNumber = detail?.ticket_number || "";
  const canTicketPdf = Boolean(ticketNumber) && lines.length > 0;
  const activityKind =
    (detail?.kind || entry.kind) === "qr_sale" ? "qr_sale" : "cash_movement";
  const ticketPdfHref = canTicketPdf
    ? `/api/backend/api/cash/activity/${encodeURIComponent(entry.id)}/ticket.pdf?kind=${activityKind}`
    : "";
  const isCashOut =
    (detail?.direction || entry.direction) === "out" &&
    !(detail?.lines && detail.lines.length > 0) &&
    !(entry.ticket_number || detail?.ticket_number);

  function downloadTicketPdf() {
    if (!ticketPdfHref) return;
    window.open(ticketPdfHref, "_blank", "noopener,noreferrer");
  }

  async function printTicketPdf() {
    if (!ticketPdfHref) return;
    try {
      const res = await fetch(ticketPdfHref);
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const frame = document.createElement("iframe");
      frame.style.position = "fixed";
      frame.style.right = "0";
      frame.style.bottom = "0";
      frame.style.width = "0";
      frame.style.height = "0";
      frame.style.border = "0";
      frame.src = url;
      document.body.appendChild(frame);
      frame.onload = () => {
        try {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        } finally {
          window.setTimeout(() => {
            URL.revokeObjectURL(url);
            frame.remove();
          }, 1500);
        }
      };
    } catch {
      // Ignore print failures; download remains available.
    }
  }

  return (
    <div
      className={styles.detailBackdrop}
      role="presentation"
      onClick={onClose}
    >
      <aside
        className={styles.detailPanel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className={styles.detailHeader}>
          <div>
            <h2 id={titleId} className={styles.panelTitle}>
              Detalle del movimiento
            </h2>
            <p className={styles.panelLead}>
              {METHOD_LABEL[method] || method}
              {detail?.affects_cash === false || entry.affects_cash === false
                ? " · no afecta efectivo"
                : null}
            </p>
          </div>
          <button type="button" className="secondary" onClick={onClose}>
            Cerrar
          </button>
        </div>

        {loading ? <p className="meta">Cargando detalle…</p> : null}
        {error ? <p className="error">{error}</p> : null}

        {!loading && !error && detail ? (
          <div className={styles.detailBody}>
            <dl className={styles.detailMeta}>
              <div>
                <dt>Estado</dt>
                <dd>{STATUS_LABEL[detail.status || ""] || detail.status || "—"}</dd>
              </div>
              <div>
                <dt>Monto</dt>
                <dd className={styles.num}>
                  {detail.amount} {detail.currency}
                </dd>
              </div>
              <div>
                <dt>Fecha</dt>
                <dd>{formatCashWhen(detail.created_at)}</dd>
              </div>
              <div>
                <dt>Registró</dt>
                <dd>{detail.recorded_by_name || "—"}</dd>
              </div>
              <div>
                <dt>Ticket</dt>
                <dd>{detail.ticket_number || "—"}</dd>
              </div>
              <div>
                <dt>Categoría</dt>
                <dd>{detail.category || "—"}</dd>
              </div>
            </dl>

            {isCashOut || detail.reason ? (
              <section className={styles.detailSection} aria-label="Motivo">
                <h3 className={styles.detailSectionTitle}>Motivo</h3>
                <p>{detail.reason || "—"}</p>
              </section>
            ) : null}

            {detail.status === "voided" ? (
              <section className={styles.detailSection} aria-label="Anulación">
                <h3 className={styles.detailSectionTitle}>Anulación</h3>
                <p>
                  {detail.void_reason || "—"}
                  {detail.voided_by_name ? (
                    <span className="meta"> · {detail.voided_by_name}</span>
                  ) : null}
                  {detail.voided_at ? (
                    <span className="meta"> · {formatCashWhen(detail.voided_at)}</span>
                  ) : null}
                </p>
              </section>
            ) : null}

            {lines.length > 0 ? (
              <section className={styles.detailSection} aria-label="Productos">
                <h3 className={styles.detailSectionTitle}>Productos</h3>
                <ul className={styles.detailLines}>
                  {lines.map((line) => {
                    const attrs = [line.talla, line.color].filter(Boolean).join(" · ");
                    return (
                      <li key={`${line.variant_sku}-${line.name}-${line.quantity}`}>
                        <div className={styles.cartLineMeta}>
                          <span className={styles.cartLineName}>{line.name || line.variant_sku}</span>
                          <span className={styles.cartLineDetail}>
                            {line.variant_sku}
                            {attrs ? ` · ${attrs}` : ""}
                            {` · ×${line.quantity}`}
                          </span>
                        </div>
                        <span className={styles.lineTotal}>
                          {line.line_total} {line.currency}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ) : null}

            {canTicketPdf ? (
              <section className={styles.detailSection} aria-label="Comprobante">
                <h3 className={styles.detailSectionTitle}>Comprobante</h3>
                <div className={styles.detailTicketActions}>
                  <button type="button" onClick={downloadTicketPdf}>
                    Descargar PDF
                  </button>
                  <button type="button" className="secondary" onClick={() => void printTicketPdf()}>
                    Imprimir
                  </button>
                  <button type="button" className="secondary" disabled title="Pronto">
                    WhatsApp
                  </button>
                  <span className={styles.ticketSoon}>Pronto</span>
                </div>
              </section>
            ) : null}

            {detail.kind === "cash_movement" ? (
              <section className={styles.detailSection} aria-label="Adjuntos">
                <h3 className={styles.detailSectionTitle}>
                  Adjuntos
                  <span className="meta">
                    {" "}
                    · {detail.attachments_count ?? attachments.length}
                  </span>
                </h3>
                {attachments.length === 0 ? (
                  <p className="meta">Sin adjuntos.</p>
                ) : (
                  <ul className={styles.detailAttachments}>
                    {attachments.map((item) => (
                      <li key={item.id}>
                        {item.filename || item.id}
                        {detail.attachments_href ? (
                          <span className="meta">
                            {" "}
                            ·{" "}
                            <a href={`/api/backend${detail.attachments_href}`}>
                              ver lista
                            </a>
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
                {attachments.length === 0 && detail.attachments_href ? (
                  <p className="meta">
                    <a href={`/api/backend${detail.attachments_href}`}>Abrir lista de adjuntos</a>
                  </p>
                ) : null}
              </section>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  );
}
