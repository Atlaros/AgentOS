"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./cash.module.css";

export const CASH_CATEGORIES = [
  { value: "venta", label: "Venta" },
  { value: "envio", label: "Envío" },
  { value: "proveedor", label: "Proveedor" },
  { value: "sueldo", label: "Sueldo" },
  { value: "servicios", label: "Servicios" },
  { value: "retiro", label: "Retiro" },
  { value: "gasto", label: "Gasto" },
  { value: "otro", label: "Otro" },
] as const;

const CASH_ERRORS: Record<string, string> = {
  session_required: "Abrí la caja antes de registrar.",
  session_open: "Ya hay una caja abierta.",
  note_required: "La nota es obligatoria si el contado no cuadra.",
  bad_pin: "PIN incorrecto.",
  pin_required: "Ingresá el PIN.",
  pin_locked: "PIN bloqueado por intentos fallidos. Probá más tarde.",
  panel_forbidden: "No tenés permiso para esta acción.",
  reason_required: "El motivo es obligatorio en salidas.",
  void_reason_required: "Indicá el motivo de la anulación.",
  out_of_stock: "Sin stock disponible.",
  disabled_variant: "Ese producto ya está vendido.",
  already_voided: "Ese movimiento ya está anulado.",
  movement_not_found: "No se encontró el movimiento.",
  ticket_not_found: "No se encontró el ticket.",
  bad_amount: "Monto inválido.",
  bad_direction: "Tipo de movimiento inválido.",
  empty: "Falta elegir un producto.",
  bad_quantity: "Cantidad inválida.",
  unknown_variant: "Prenda no encontrada.",
  unknown_modifier: "Ese extra no está en el catálogo.",
  bad_price: "El precio no es válido.",
  bad_discount: "Ese descuento no es válido.",
  discount_exceeds: "El descuento no puede superar el total.",
  bad_method: "Método no soportado.",
  bad_cash: "No se pudo registrar el movimiento.",
  table_required: "Indicá la mesa.",
  bad_table: "Ese nombre de mesa no sirve.",
  unknown_tab: "No se encontró esa mesa.",
  not_open: "Esa mesa ya no está abierta.",
};

export function mapCashError(detail: string, fallback: string): string {
  return CASH_ERRORS[detail] || fallback;
}

export async function readCashDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : "";
  } catch {
    return "";
  }
}

export function formatCashWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("es-BO", { dateStyle: "short", timeStyle: "short" });
}

export function CashForm() {
  const router = useRouter();
  const [direction, setDirection] = useState<"in" | "out">("in");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const nextDirection = String(data.get("direction") || "in") as "in" | "out";
    const reason = String(data.get("reason") || "").trim();
    if (nextDirection === "out" && !reason) {
      setError(mapCashError("reason_required", "El motivo es obligatorio en salidas."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/cash", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          direction: nextDirection,
          amount: String(data.get("amount") || "").trim(),
          reason,
          category: String(data.get("category") || "").trim(),
          method: "cash",
        }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo registrar el movimiento."));
        return;
      }
      form.reset();
      setDirection("in");
      router.refresh();
    } catch {
      setError("No se pudo registrar el movimiento.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="cash-manual-title">
      <h2 id="cash-manual-title" className={styles.panelTitle}>
        Movimiento manual
      </h2>
      <p className={styles.panelLead}>Entrada o salida de efectivo del turno. Método: efectivo.</p>
      <form className="product-form" onSubmit={onSubmit}>
        <label>
          Tipo
          <select
            name="direction"
            value={direction}
            onChange={(event) => setDirection(event.target.value === "out" ? "out" : "in")}
            required
          >
            <option value="in">Entrada</option>
            <option value="out">Salida</option>
          </select>
        </label>
        <label>
          Monto (BOB)
          <input name="amount" type="number" step="0.01" min="0.01" required placeholder="50" />
        </label>
        <label>
          Categoría
          <select name="category" defaultValue="otro" required>
            {CASH_CATEGORIES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="wide">
          Motivo{direction === "out" ? " (obligatorio)" : ""}
          <input
            name="reason"
            placeholder={direction === "out" ? "Envío, sueldo, retiro…" : "Opcional"}
            required={direction === "out"}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "…" : "Registrar"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </section>
  );
}
