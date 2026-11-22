"use client";

import { useEffect, useRef } from "react";

import styles from "./cash.module.css";

export type TicketDrawerLine = {
  name: string;
  quantity: number;
  unit: string;
  total: string;
};

export type TicketDrawerModel = {
  ticketNumber?: string;
  tableLabel?: string;
  method?: string;
  status?: string;
  lines: TicketDrawerLine[];
  discount?: string;
  total: string;
  currency?: string;
  tendered?: string;
  change?: string;
  pdfHref?: string;
};

type TicketDrawerProps = {
  model: TicketDrawerModel;
  onClose: () => void;
  embedded?: boolean;
};

export function TicketDrawer({ model, onClose, embedded = false }: TicketDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const currency = model.currency || "BOB";

  useEffect(() => {
    if (!embedded) closeRef.current?.focus();
  }, [embedded]);

  useEffect(() => {
    if (embedded) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [embedded, onClose]);

  const panel = (
    <aside
      className={embedded ? styles.ticketDrawerEmbedded : styles.ticketDrawer}
      role="dialog"
      aria-modal={embedded ? false : true}
      aria-labelledby="cash-ticket-drawer-title"
    >
      <div className={styles.ticketDrawerBody}>
        <header className={styles.ticketDrawerHeader}>
          <div>
            <p className={styles.ticketDrawerKicker}>No es factura fiscal</p>
            <h3 id="cash-ticket-drawer-title" className={styles.ticketDrawerTitle}>
              Comprobante de venta
            </h3>
          </div>
          <button ref={closeRef} type="button" className="secondary" onClick={onClose}>
            Cerrar
          </button>
        </header>

        {model.status === "Por confirmar" ? (
          <p className={styles.ticketDrawerLead}>Revisá el detalle. Confirmar sigue en el cobro.</p>
        ) : null}

        <dl className={styles.ticketMeta}>
          {model.ticketNumber ? (
            <div>
              <dt>Ticket Nº</dt>
              <dd>{model.ticketNumber}</dd>
            </div>
          ) : null}
          {model.tableLabel ? (
            <div>
              <dt>Mesa</dt>
              <dd>{model.tableLabel}</dd>
            </div>
          ) : null}
          {model.method ? (
            <div>
              <dt>Método</dt>
              <dd>{model.method}</dd>
            </div>
          ) : null}
          {model.status ? (
            <div>
              <dt>Estado</dt>
              <dd>{model.status}</dd>
            </div>
          ) : null}
        </dl>

        {model.lines.length === 0 ? (
          <p className={styles.ticketEmpty}>Sin ítems en este comprobante.</p>
        ) : (
          <table className={styles.ticketTable}>
            <thead>
              <tr>
                <th>Cant.</th>
                <th>Producto</th>
                <th>P.unit</th>
                <th>Importe</th>
              </tr>
            </thead>
            <tbody>
              {model.lines.map((line, index) => (
                <tr key={`${line.name}-${index}`}>
                  <td>{line.quantity}</td>
                  <td>{line.name}</td>
                  <td>{line.unit}</td>
                  <td>{line.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {model.discount ? (
          <p className={styles.ticketDiscountRow}>
            Descuento <strong className={styles.num}>{model.discount} {currency}</strong>
          </p>
        ) : null}

        <p className={styles.ticketDrawerTotal}>
          Total
          <strong>
            {model.total} {currency}
          </strong>
        </p>

        {model.tendered ? (
          <p className={styles.ticketTenderRow}>
            Entregado <span className={styles.num}>{model.tendered} {currency}</span>
          </p>
        ) : null}
        {model.change ? (
          <p className={styles.ticketTenderRow}>
            Vuelto <span className={styles.num}>{model.change} {currency}</span>
          </p>
        ) : null}

        {model.pdfHref ? (
          <a className={styles.ticketPdfLink} href={model.pdfHref} target="_blank" rel="noopener noreferrer">
            Descargar PDF
          </a>
        ) : null}

        <p className={styles.ticketDrawerFoot}>Gracias por su compra. No es factura fiscal.</p>
      </div>
    </aside>
  );

  if (embedded) return panel;

  return (
    <div className={styles.ticketDrawerRoot}>
      <button
        type="button"
        className={styles.ticketDrawerBackdrop}
        aria-label="Cerrar comprobante"
        onClick={onClose}
      />
      {panel}
    </div>
  );
}
