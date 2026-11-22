"use client";

import { useEffect, useMemo, useState } from "react";

import { OrderAttachments } from "../orders/order-attachments";

import styles from "./suppliers.module.css";

export type PurchaseOrderRow = {
  id: string;
  number: string;
  supplier_id: string;
  status: string;
  payment_status?: string;
  amount_paid?: string;
  notes?: string;
  line_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PurchaseOrderLine = {
  id: string;
  variant_sku: string;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost?: string | null;
  currency: string;
};

export type PurchaseOrderDetail = PurchaseOrderRow & {
  lines: PurchaseOrderLine[];
};

type OrdersPanelProps = {
  orders: PurchaseOrderRow[];
  supplierNames: Record<string, string>;
};

type ReceiveDraft = Record<string, { qty: string; cost: string }>;

const STATUS_LABEL: Record<string, string> = {
  draft: "Borrador",
  sent: "Enviado",
  partially_received: "Recibo parcial",
  received: "Recibido",
  cancelled: "Cancelado",
};

const PAYMENT_LABEL: Record<string, string> = {
  unpaid: "Impago",
  partial: "Pago parcial",
  paid: "Pagado",
};

const ERROR_TEXT: Record<string, string> = {
  bad_status: "Ese cambio de estado no está permitido.",
  over_receive: "La cantidad supera lo que falta recibir.",
  nothing_to_pay: "Este pedido no tiene saldo a crédito.",
  bad_amount: "El monto no es válido.",
  session_required: "Abrí la caja para pagar en efectivo.",
  bad_unit_cost: "Falta un costo válido.",
  bad_payment_method: "Forma de pago no válida.",
  purchase_order_not_found: "No se encontró el pedido.",
  empty_lines: "Indicá al menos una línea para recibir.",
  supplier_number_missing: "El proveedor no tiene WhatsApp ni teléfono.",
  send_failed: "No se pudo enviar por WhatsApp. El pedido sigue en borrador.",
};

type SendWhatsappPreview = {
  body: string;
  wa_number: string;
  supplier_name: string;
  order_id: string;
  number?: string;
  can_send: boolean;
};

function statusLabel(status: string): string {
  return STATUS_LABEL[status] || status;
}

function paymentLabel(status?: string): string {
  if (!status) return "Impago";
  return PAYMENT_LABEL[status] || status;
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return value;
  return stamp.toLocaleDateString("es-BO", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function money(value?: string | null): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function receivedValue(detail: PurchaseOrderDetail): number {
  return (detail.lines || []).reduce((sum, line) => {
    return sum + money(line.unit_cost) * line.quantity_received;
  }, 0);
}

function outstanding(detail: PurchaseOrderDetail): number {
  return Math.max(0, receivedValue(detail) - money(detail.amount_paid));
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return ERROR_TEXT[body.detail] || "No se pudo guardar el cambio.";
    }
  } catch {
    /* response was not JSON */
  }
  return "No se pudo guardar el cambio.";
}

function orderClipboardText(
  detail: PurchaseOrderDetail,
  supplierName: string,
): string {
  const lines = (detail.lines || []).map((line) => {
    const cost =
      line.unit_cost != null ? `${line.unit_cost} ${line.currency}` : "sin costo";
    return `- ${line.variant_sku}: pedida ${line.quantity_ordered}, recibida ${line.quantity_received}, costo ${cost}`;
  });
  return [
    detail.number,
    `Proveedor: ${supplierName}`,
    `Estado: ${statusLabel(detail.status)}`,
    `Pago: ${paymentLabel(detail.payment_status)} (${detail.amount_paid || "0"} BOB)`,
    detail.notes ? `Notas: ${detail.notes}` : "",
    ...lines,
  ]
    .filter(Boolean)
    .join("\n");
}

export function OrdersPanel({ orders, supplierNames }: OrdersPanelProps) {
  const [rows, setRows] = useState(orders);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PurchaseOrderDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [receiveDraft, setReceiveDraft] = useState<ReceiveDraft>({});
  const [receiveMethod, setReceiveMethod] = useState<"cash" | "credit">("credit");
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState<"cash" | "transfer">("transfer");
  const [sendPreview, setSendPreview] = useState<SendWhatsappPreview | null>(null);

  useEffect(() => {
    setRows(orders);
  }, [orders]);

  const sorted = useMemo(
    () =>
      [...rows].sort((a, b) => {
        const left = a.created_at || "";
        const right = b.created_at || "";
        return right.localeCompare(left);
      }),
    [rows],
  );

  async function reload(id: string) {
    const [listRes, detailRes] = await Promise.all([
      fetch("/api/backend/api/purchase-orders", { cache: "no-store" }),
      fetch(`/api/backend/api/purchase-orders/${encodeURIComponent(id)}`, {
        cache: "no-store",
      }),
    ]);
    if (!listRes.ok || !detailRes.ok) {
      setError("No se pudo actualizar el pedido.");
      return;
    }
    const listBody = (await listRes.json()) as { purchase_orders?: PurchaseOrderRow[] };
    const detailBody = (await detailRes.json()) as PurchaseOrderDetail;
    setRows(listBody.purchase_orders || []);
    setDetail(detailBody);
    setSelectedId(id);
  }

  async function openDetail(id: string) {
    setSelectedId(id);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`/api/backend/api/purchase-orders/${encodeURIComponent(id)}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        setDetail(null);
        setError("No se pudo cargar el detalle.");
        return;
      }
      const body = (await res.json()) as PurchaseOrderDetail;
      setDetail(body);
    } catch {
      setDetail(null);
      setError("Error de red al cargar el pedido.");
    } finally {
      setBusy(false);
    }
  }

  async function patchStatus(status: "cancelled") {
    if (!detail) return;
    setBusy(true);
    setError("");
    setNotice("");
    setSendPreview(null);
    try {
      const res = await fetch(`/api/backend/api/purchase-orders/${detail.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      await reload(detail.id);
    } catch {
      setError("Error de red al actualizar el pedido.");
    } finally {
      setBusy(false);
    }
  }

  async function requestSendPreview() {
    if (!detail) return;
    setBusy(true);
    setError("");
    setNotice("");
    setSendPreview(null);
    try {
      const res = await fetch(
        `/api/backend/api/purchase-orders/${encodeURIComponent(detail.id)}/send-whatsapp`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: false }),
        },
      );
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      const body = (await res.json()) as SendWhatsappPreview;
      setSendPreview(body);
    } catch {
      setError("No se pudo preparar el envío al proveedor.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmSendWhatsapp() {
    if (!detail || !sendPreview) return;
    if (!sendPreview.can_send) {
      setError("El proveedor no tiene WhatsApp ni teléfono.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(
        `/api/backend/api/purchase-orders/${encodeURIComponent(detail.id)}/send-whatsapp`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: true }),
        },
      );
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setSendPreview(null);
      setNotice("Pedido enviado al proveedor por WhatsApp.");
      await reload(detail.id);
    } catch {
      setError("No se pudo enviar el pedido al proveedor.");
    } finally {
      setBusy(false);
    }
  }

  function openReceive() {
    if (!detail) return;
    const next: ReceiveDraft = {};
    for (const line of detail.lines || []) {
      const remaining = line.quantity_ordered - line.quantity_received;
      if (remaining > 0) {
        next[line.id] = { qty: String(remaining), cost: line.unit_cost ?? "" };
      }
    }
    setReceiveDraft(next);
    setReceiveMethod("credit");
    setReceiveOpen(true);
  }

  async function submitReceive() {
    if (!detail) return;
    const lines = (detail.lines || [])
      .map((line) => {
        const draft = receiveDraft[line.id];
        const quantity = Number(draft?.qty || 0);
        if (!Number.isFinite(quantity) || quantity < 1) return null;
        return {
          variant_sku: line.variant_sku,
          quantity,
          unit_cost: (draft?.cost || "").trim() || undefined,
        };
      })
      .filter((line) => line !== null);
    if (lines.length === 0) {
      setError("Indicá al menos una línea para recibir.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`/api/backend/api/purchase-orders/${detail.id}/receive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lines, payment_method: receiveMethod }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setReceiveOpen(false);
      await reload(detail.id);
    } catch {
      setError("Error de red al recibir el pedido.");
    } finally {
      setBusy(false);
    }
  }

  function openPayment() {
    if (!detail) return;
    const due = outstanding(detail);
    setPayAmount(due > 0 ? due.toFixed(2) : "");
    setPayMethod("transfer");
    setPayOpen(true);
  }

  async function submitPayment() {
    if (!detail) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`/api/backend/api/purchase-orders/${detail.id}/payments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount: payAmount.trim(),
          method: payMethod,
          currency: "BOB",
        }),
      });
      if (!res.ok) {
        setError(await errorMessage(res));
        return;
      }
      setPayOpen(false);
      await reload(detail.id);
    } catch {
      setError("Error de red al registrar el pago.");
    } finally {
      setBusy(false);
    }
  }

  async function copyOrder() {
    if (!detail) return;
    const supplier = supplierNames[detail.supplier_id] || detail.supplier_id;
    try {
      await navigator.clipboard.writeText(orderClipboardText(detail, supplier));
      setNotice("Pedido copiado.");
      setError("");
    } catch {
      setError("No se pudo copiar el pedido.");
    }
  }

  const canReceive =
    detail?.status === "sent" || detail?.status === "partially_received";
  const canPay =
    !!detail &&
    (detail.payment_status === "unpaid" || detail.payment_status === "partial") &&
    (detail.lines || []).some((line) => line.quantity_received > 0);

  return (
    <div className={styles.ordersWrap}>
      <p className="lead">
        Enviá el pedido, recibí parcial o total y registrá el pago al proveedor. El
        asiento nace al recibir, no al enviar.
      </p>
      {error ? <p className="error">{error}</p> : null}
      {notice ? <p className={styles.okBanner}>{notice}</p> : null}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Nº</th>
              <th>Proveedor</th>
              <th>Fecha</th>
              <th>Estado</th>
              <th>Pago</th>
              <th>Líneas</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={6}>Sin órdenes todavía. Generá un borrador desde Reposición.</td>
              </tr>
            ) : (
              sorted.map((row) => (
                <tr
                  key={row.id}
                  className={
                    selectedId === row.id ? styles.rowSelected : styles.rowClickable
                  }
                  onClick={() => void openDetail(row.id)}
                >
                  <td>
                    <code>{row.number || row.id.slice(0, 8)}</code>
                  </td>
                  <td>{supplierNames[row.supplier_id] || row.supplier_id}</td>
                  <td>{formatDate(row.created_at)}</td>
                  <td>{statusLabel(row.status)}</td>
                  <td>{paymentLabel(row.payment_status)}</td>
                  <td>{row.line_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {busy ? <p className="meta">Cargando…</p> : null}
      {detail ? (
        <section className={styles.panel}>
          <h3 className={styles.panelTitle}>
            {detail.number} · {statusLabel(detail.status)}
          </h3>
          <p className={styles.muted}>
            Proveedor: {supplierNames[detail.supplier_id] || detail.supplier_id}
            {" · "}
            Pago: {paymentLabel(detail.payment_status)} ({detail.amount_paid || "0"} BOB)
            {detail.notes ? ` · ${detail.notes}` : ""}
          </p>
          <div className={styles.actions}>
            {detail.status === "draft" ? (
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={busy}
                onClick={() => void requestSendPreview()}
              >
                Enviar
              </button>
            ) : null}
            {detail.status === "draft" || detail.status === "sent" ? (
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={busy}
                onClick={() => void patchStatus("cancelled")}
              >
                Cancelar
              </button>
            ) : null}
            {canReceive ? (
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={busy}
                onClick={openReceive}
              >
                Recibir
              </button>
            ) : null}
            {canPay ? (
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={busy}
                onClick={openPayment}
              >
                Registrar pago
              </button>
            ) : null}
            <button type="button" className={styles.ghostBtn} onClick={() => void copyOrder()}>
              Copiar
            </button>
          </div>
          {sendPreview && detail.status === "draft" ? (
            <div className={styles.confirmBox} role="region" aria-label="Confirmar envío al proveedor">
              {!sendPreview.can_send ? (
                <p className={styles.confirmWarn}>
                  Agregá WhatsApp o teléfono del proveedor en el directorio antes de enviar.
                </p>
              ) : null}
              <p className={styles.confirmMeta}>
                {sendPreview.supplier_name} · {sendPreview.wa_number || "sin número"}
              </p>
              <p className={styles.confirmText}>{sendPreview.body}</p>
              <div className={styles.confirmActions}>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  disabled={busy || !sendPreview.can_send}
                  onClick={() => void confirmSendWhatsapp()}
                >
                  Confirmar envío
                </button>
                <button
                  type="button"
                  className={styles.ghostBtn}
                  disabled={busy}
                  onClick={() => setSendPreview(null)}
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : null}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Pedida</th>
                  <th>Recibida</th>
                  <th>Costo</th>
                </tr>
              </thead>
              <tbody>
                {(detail.lines || []).map((line) => (
                  <tr key={line.id}>
                    <td>
                      <code>{line.variant_sku}</code>
                    </td>
                    <td>{line.quantity_ordered}</td>
                    <td>{line.quantity_received}</td>
                    <td>
                      {line.unit_cost != null
                        ? `${line.unit_cost} ${line.currency}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <OrderAttachments
            orderId={detail.id}
            apiPath={`/api/purchase-orders/${encodeURIComponent(detail.id)}/attachments`}
            title="Adjuntos de la OC"
          />
        </section>
      ) : null}

      {receiveOpen && detail ? (
        <div className={styles.modalBackdrop} role="presentation">
          <div className={styles.modal} role="dialog" aria-labelledby="receive-title">
            <h3 id="receive-title" className={styles.panelTitle}>
              Recibir {detail.number}
            </h3>
            {(detail.lines || [])
              .filter((line) => line.quantity_ordered - line.quantity_received > 0)
              .map((line) => {
                const remaining = line.quantity_ordered - line.quantity_received;
                const draft = receiveDraft[line.id] || { qty: String(remaining), cost: "" };
                return (
                  <div key={line.id} className={styles.receiveLine}>
                    <code>{line.variant_sku}</code>
                    <span className={styles.muted}>faltan {remaining}</span>
                    <label className={styles.fieldLabel}>
                      Cantidad
                      <input
                        className={styles.qtyInput}
                        inputMode="numeric"
                        value={draft.qty}
                        onChange={(event) =>
                          setReceiveDraft((current) => ({
                            ...current,
                            [line.id]: { ...draft, qty: event.target.value },
                          }))
                        }
                      />
                    </label>
                    <label className={styles.fieldLabel}>
                      Costo
                      <input
                        className={styles.qtyInput}
                        inputMode="decimal"
                        value={draft.cost}
                        onChange={(event) =>
                          setReceiveDraft((current) => ({
                            ...current,
                            [line.id]: { ...draft, cost: event.target.value },
                          }))
                        }
                      />
                    </label>
                  </div>
                );
              })}
            <label className={styles.fieldLabel}>
              Forma de pago al recibir
              <select
                value={receiveMethod}
                onChange={(event) =>
                  setReceiveMethod(event.target.value === "cash" ? "cash" : "credit")
                }
              >
                <option value="credit">Crédito</option>
                <option value="cash">Contado</option>
              </select>
            </label>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={busy}
                onClick={() => void submitReceive()}
              >
                Confirmar recepción
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                onClick={() => setReceiveOpen(false)}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {payOpen && detail ? (
        <div className={styles.modalBackdrop} role="presentation">
          <div className={styles.modal} role="dialog" aria-labelledby="pay-title">
            <h3 id="pay-title" className={styles.panelTitle}>
              Registrar pago
            </h3>
            <p className={styles.muted}>
              Saldo pendiente: {outstanding(detail).toFixed(2)} BOB
            </p>
            <label className={styles.fieldLabel}>
              Monto
              <input
                className={styles.qtyInput}
                inputMode="decimal"
                value={payAmount}
                onChange={(event) => setPayAmount(event.target.value)}
              />
            </label>
            <label className={styles.fieldLabel}>
              Medio
              <select
                value={payMethod}
                onChange={(event) =>
                  setPayMethod(event.target.value === "cash" ? "cash" : "transfer")
                }
              >
                <option value="transfer">Transferencia</option>
                <option value="cash">Efectivo (caja)</option>
              </select>
            </label>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.primaryBtn}
                disabled={busy}
                onClick={() => void submitPayment()}
              >
                Guardar pago
              </button>
              <button type="button" className={styles.ghostBtn} onClick={() => setPayOpen(false)}>
                Cerrar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
