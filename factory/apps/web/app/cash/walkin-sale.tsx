"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";

import { ProductThumb } from "@/components/product-thumb";

import { mapCashError, readCashDetail } from "./cash-form";
import styles from "./cash.module.css";
import { TicketDrawer, type TicketDrawerLine, type TicketDrawerModel } from "./ticket-drawer";

type GridVariant = {
  variant_sku: string;
  name: string;
  price: string;
  currency: string;
  stock: number;
  talla?: string;
  color?: string;
  sold_out?: boolean;
  selectable?: boolean;
};

type GridProduct = {
  product_sku: string;
  name: string;
  category: string;
  initial?: string;
  image_url?: string;
  media_id?: string;
  thumb_url?: string;
  price: string;
  currency: string;
  sold_out?: boolean;
  variant_count?: number;
  variants: GridVariant[];
};

type CategoryChip = {
  name: string;
  sort_order?: number | null;
};

type OpenTab = {
  id: string;
  table_label: string;
  status: string;
  items?: { name?: string; quantity?: number; unit_price?: string; currency?: string }[];
};

type CartLine = {
  key: string;
  variant_sku: string;
  codigo?: string;
  name: string;
  unitPrice: string;
  currency: string;
  stock: number;
  quantity: number;
  optionIds: string[];
};

type ModifierChoice = {
  id: string;
  name: string;
  price_delta: string;
  currency?: string;
};

type TicketLine = {
  variant_sku?: string;
  name?: string;
  quantity?: number;
  unit_price?: string;
  currency?: string;
  line_total?: string;
};

type QrWaiting = {
  id: string;
  number?: string;
  status?: string;
  qr?: string | null;
  provider_ref?: string | null;
  total?: string;
  currency?: string;
  lines?: TicketLine[];
};

type PayMethod = "cash" | "qr";
type PayPhase = "method" | "waiting";

type SaleTicketBody = {
  number?: string;
  movement_id?: string | null;
  total?: string;
  currency?: string;
  discount_amount?: string;
  method?: string;
  lines?: TicketLine[];
};

function movementPdfHref(movementId: string): string {
  return `/api/backend/api/cash/activity/${encodeURIComponent(movementId)}/ticket.pdf?kind=cash_movement`;
}

function discountText(raw: string | number | undefined | null): string | undefined {
  const amount = parseMoney(raw);
  if (!Number.isFinite(amount) || amount <= 0) return undefined;
  return formatBob(amount);
}

function linesFromTicket(lines: TicketLine[] | undefined): TicketDrawerLine[] {
  return (lines || []).map((line) => ({
    name: line.name || line.variant_sku || "Ítem",
    quantity: line.quantity && line.quantity > 0 ? line.quantity : 1,
    unit: line.unit_price || "—",
    total: line.line_total || line.unit_price || "—",
  }));
}

function linesFromTab(tab: OpenTab | undefined): TicketDrawerLine[] {
  return (tab?.items || []).map((item) => {
    const quantity = item.quantity && item.quantity > 0 ? item.quantity : 1;
    const unitAmount = parseMoney(item.unit_price);
    const unit = Number.isFinite(unitAmount) ? formatBob(unitAmount) : item.unit_price || "—";
    const total = Number.isFinite(unitAmount) ? formatBob(unitAmount * quantity) : "—";
    return { name: item.name || "Ítem", quantity, unit, total };
  });
}

function sumDrawerLines(lines: TicketDrawerLine[]): string {
  let sum = 0;
  for (const line of lines) {
    const amount = parseMoney(line.total);
    if (!Number.isFinite(amount)) return "—";
    sum += amount;
  }
  return formatBob(sum);
}

function cartKey(sku: string, optionIds: string[]): string {
  return `${sku}::${[...optionIds].sort().join(",")}`;
}

function skuUsed(lines: CartLine[], sku: string, exceptKey?: string): number {
  return lines
    .filter((line) => line.variant_sku === sku && line.key !== exceptKey)
    .reduce((sum, line) => sum + line.quantity, 0);
}

function lineUnit(line: CartLine, modifiers: ModifierChoice[]): number {
  const base = parseMoney(line.unitPrice);
  if (!Number.isFinite(base)) return Number.NaN;
  const extra = line.optionIds.reduce((sum, id) => {
    const found = modifiers.find((item) => item.id === id);
    const delta = found ? parseMoney(found.price_delta) : 0;
    return sum + (Number.isFinite(delta) ? delta : 0);
  }, 0);
  return base + extra;
}

function parseMoney(value: string | number | undefined | null): number {
  if (value === undefined || value === null) return Number.NaN;
  const text = String(value).trim().replace(",", ".");
  if (!text) return Number.NaN;
  const amount = Number(text);
  return Number.isFinite(amount) ? amount : Number.NaN;
}

function formatBob(amount: number): string {
  if (!Number.isFinite(amount)) return "0.00";
  return amount.toFixed(2);
}

function selectableVariants(product: GridProduct): GridVariant[] {
  // Trust API `selectable` (services with tracks_stock=false may have stock 0).
  return product.variants.filter((variant) => variant.selectable === true);
}

function stockCap(variant: GridVariant): number {
  const stock = hitStock(variant);
  if (stock >= 1) return stock;
  // Selectable with zero stock = non-tracking service; allow multiple lines.
  return variant.selectable === true ? Number.MAX_SAFE_INTEGER : 0;
}

function pickFromGrid(products: GridProduct[], query: string): { variant: GridVariant | null; product: GridProduct | null } {
  const needle = query.trim().toLowerCase();
  const variants = products.flatMap((product) => product.variants);
  const exact = variants.find((variant) => variant.variant_sku.trim().toLowerCase() === needle);
  if (exact) return { variant: exact, product: null };
  const byProduct = products.find((product) => product.product_sku.trim().toLowerCase() === needle);
  const chosen = byProduct ?? (products.length === 1 ? products[0] : null);
  if (!chosen) return { variant: null, product: null };
  const open = selectableVariants(chosen);
  if (open.length === 1) return { variant: open[0], product: null };
  if (open.length > 1) return { variant: null, product: chosen };
  return { variant: null, product: null };
}

function hitStock(hit: { stock?: number }): number {
  return typeof hit.stock === "number" && Number.isFinite(hit.stock) ? Math.max(0, hit.stock) : 0;
}

/** Turn Baneco/base64 or data-URL payloads into an <img> src; null for fake text QR. */
function qrImageSrc(payload: string | null | undefined): string | null {
  if (!payload) return null;
  const trimmed = payload.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("data:image")) return trimmed;
  if (trimmed.startsWith("QR:")) return null;
  const compact = trimmed.replace(/\s+/g, "");
  if (compact.length < 64 || !/^[A-Za-z0-9+/=]+$/.test(compact)) return null;
  if (compact.startsWith("/9j/")) return `data:image/jpeg;base64,${compact}`;
  if (compact.startsWith("iVBOR")) return `data:image/png;base64,${compact}`;
  // Long opaque base64 without a clear magic — still treat as PNG for Baneco-style dumps.
  if (compact.length >= 200) return `data:image/png;base64,${compact}`;
  return null;
}

export function WalkinSale() {
  const router = useRouter();
  const searchRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<GridProduct[]>([]);
  const [categories, setCategories] = useState<CategoryChip[]>([]);
  const [category, setCategory] = useState("Todo");
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [modifiers, setModifiers] = useState<ModifierChoice[]>([]);
  const [tableName, setTableName] = useState("");
  const [picker, setPicker] = useState<GridProduct | null>(null);
  const [revision, setRevision] = useState(0);
  const [searching, setSearching] = useState(true);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ticketNumber, setTicketNumber] = useState("");
  const [ticketPdfHref, setTicketPdfHref] = useState("");
  const [qrWaiting, setQrWaiting] = useState<QrWaiting | null>(null);
  const [payOpen, setPayOpen] = useState(false);
  const [payPhase, setPayPhase] = useState<PayPhase>("method");
  const [payMethod, setPayMethod] = useState<PayMethod>("cash");
  const [tendered, setTendered] = useState("");
  const [discount, setDiscount] = useState("");
  const [discountPin, setDiscountPin] = useState("");
  const [savedPreview, setSavedPreview] = useState<TicketDrawerModel | null>(null);
  const [hideCashPreview, setHideCashPreview] = useState(false);

  const waiting = payOpen && payPhase === "waiting" && qrWaiting != null;

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setSearching(true);
      const params = new URLSearchParams();
      const q = query.trim();
      if (q) params.set("q", q);
      if (category !== "Todo") params.set("category", category);
      try {
        const res = await fetch(`/api/backend/api/cash/grid?${params.toString()}`, { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled) setProducts([]);
          return;
        }
        const body = (await res.json()) as { products?: GridProduct[] };
        if (!cancelled) setProducts(Array.isArray(body.products) ? body.products : []);
      } catch {
        if (!cancelled) setProducts([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, query.trim() ? 200 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [query, category, revision]);

  useEffect(() => {
    let cancelled = false;
    async function loadSide() {
      try {
        const [catRes, tabRes, modRes] = await Promise.all([
          fetch("/api/backend/api/catalog/categories", { cache: "no-store" }),
          fetch("/api/backend/api/cash/tabs", { cache: "no-store" }),
          fetch("/api/backend/api/catalog/modifiers", { cache: "no-store" }),
        ]);
        if (cancelled) return;
        if (catRes.ok) {
          const body = (await catRes.json()) as { categories?: CategoryChip[] };
          setCategories(Array.isArray(body.categories) ? body.categories : []);
        }
        if (tabRes.ok) {
          const body = (await tabRes.json()) as { tabs?: OpenTab[] };
          setTabs(Array.isArray(body.tabs) ? body.tabs : []);
        }
        if (modRes.ok) {
          const body = (await modRes.json()) as { modifiers?: ModifierChoice[] };
          setModifiers(Array.isArray(body.modifiers) ? body.modifiers : []);
        }
      } catch {
        if (!cancelled) setTabs([]);
      }
    }
    void loadSide();
    return () => {
      cancelled = true;
    };
  }, [revision]);

  useEffect(() => {
    if (!waiting || !qrWaiting?.id) return;
    let cancelled = false;

    async function pollStatus() {
      const saleId = qrWaiting?.id;
      if (!saleId || cancelled) return;
      try {
        const checkRes = await fetch(`/api/backend/api/cash/sales/${encodeURIComponent(saleId)}/check`, {
          method: "POST",
          cache: "no-store",
        });
        let body: QrWaiting | null = null;
        if (checkRes.ok) {
          body = (await checkRes.json()) as QrWaiting;
        } else {
          const getRes = await fetch(`/api/backend/api/cash/sales/${encodeURIComponent(saleId)}`, {
            cache: "no-store",
          });
          if (!getRes.ok) return;
          body = (await getRes.json()) as QrWaiting;
        }
        if (cancelled || !body) return;
        if (body.status === "recorded") {
          setTicketNumber(body.number || "");
          if (body.id) {
            setTicketPdfHref(
              `/api/backend/api/cash/activity/${encodeURIComponent(body.id)}/ticket.pdf?kind=qr_sale`,
            );
          } else {
            setTicketPdfHref("");
          }
          setCart([]);
          setQuery("");
          setRevision((value) => value + 1);
          setQrWaiting(null);
          setPayPhase("method");
          setPayOpen(false);
          setTendered("");
          setError("");
          router.refresh();
        } else if (body.status === "pending_qr") {
          setQrWaiting((prev) =>
            prev
              ? {
                  ...prev,
                  ...body,
                  id: body.id || prev.id,
                  qr: body.qr ?? prev.qr,
                }
              : prev,
          );
        }
      } catch {
        // Keep waiting; next poll retries.
      }
    }

    void pollStatus();
    const handle = window.setInterval(() => {
      void pollStatus();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [waiting, qrWaiting?.id, router]);

  const cartTotal = useMemo(() => {
    return cart.reduce((sum, line) => {
      const unit = lineUnit(line, modifiers);
      if (!Number.isFinite(unit)) return sum;
      return sum + unit * line.quantity;
    }, 0);
  }, [cart, modifiers]);

  const tenderedAmount = parseMoney(tendered);
  const discountAmount = parseMoney(discount);
  const discountApplied = Number.isFinite(discountAmount) && discountAmount > 0;
  const amountDue = Math.max(0, cartTotal - (discountApplied ? discountAmount : 0));
  const changeDue =
    Number.isFinite(tenderedAmount) ? tenderedAmount - amountDue : Number.NaN;
  const cashConfirmOk =
    Number.isFinite(tenderedAmount) &&
    tenderedAmount + 1e-9 >= amountDue &&
    amountDue > 0 &&
    (!discountApplied || discountAmount <= cartTotal + 1e-9);

  const waitingLines: TicketLine[] =
    qrWaiting?.lines && qrWaiting.lines.length > 0
      ? qrWaiting.lines
      : cart.map((line) => ({
          variant_sku: line.variant_sku,
          name: line.name,
          quantity: line.quantity,
          unit_price: formatBob(lineUnit(line, modifiers)),
          currency: line.currency,
          line_total: formatBob(lineUnit(line, modifiers) * line.quantity),
        }));
  const waitingTotal = qrWaiting?.total || formatBob(cartTotal);
  const waitingCurrency = qrWaiting?.currency || "BOB";
  const waitingQrSrc = qrImageSrc(qrWaiting?.qr);

  function addVariant(variant: GridVariant) {
    if (waiting) return;
    if (variant.sold_out || variant.selectable === false) return;
    const stock = stockCap(variant);
    if (stock < 1) return;
    setError("");
    setTicketNumber("");
    setTicketPdfHref("");
    setPicker(null);
    setCart((prev) => {
      const key = cartKey(variant.variant_sku, []);
      if (skuUsed(prev, variant.variant_sku) >= stock) return prev;
      const existing = prev.find((line) => line.key === key);
      if (existing) {
        return prev.map((line) =>
          line.key === key ? { ...line, quantity: line.quantity + 1 } : line,
        );
      }
      const detail = [variant.talla, variant.color].filter(Boolean).join(" · ");
      return [
        ...prev,
        {
          key,
          variant_sku: variant.variant_sku,
          codigo: variant.variant_sku,
          name: detail ? `${variant.name} · ${detail}` : variant.name,
          unitPrice: variant.price,
          currency: variant.currency || "BOB",
          stock,
          quantity: 1,
          optionIds: [],
        },
      ];
    });
  }

  function openProduct(product: GridProduct) {
    if (waiting) return;
    const open = selectableVariants(product);
    if (open.length === 0) return;
    if (open.length === 1) {
      addVariant(open[0]);
      return;
    }
    setPicker(product);
  }

  function setLineQty(key: string, nextQty: number) {
    if (waiting) return;
    setCart((prev) =>
      prev
        .map((line) => {
          if (line.key !== key) return line;
          const room = line.stock - skuUsed(prev, line.variant_sku, key);
          const capped = Math.min(Math.max(0, nextQty), Math.max(0, room));
          return { ...line, quantity: capped };
        })
        .filter((line) => line.quantity > 0),
    );
  }

  function removeLine(key: string) {
    if (waiting) return;
    setCart((prev) => prev.filter((line) => line.key !== key));
  }

  function toggleOption(key: string, modifierId: string) {
    if (waiting) return;
    setCart((prev) => {
      const current = prev.find((line) => line.key === key);
      if (!current) return prev;
      const nextIds = current.optionIds.includes(modifierId)
        ? current.optionIds.filter((id) => id !== modifierId)
        : [...current.optionIds, modifierId];
      const nextKey = cartKey(current.variant_sku, nextIds);
      const without = prev.filter((line) => line.key !== key);
      const twin = without.find((line) => line.key === nextKey);
      if (twin) {
        const room = current.stock - skuUsed(without, current.variant_sku, twin.key);
        const quantity = Math.min(twin.quantity + current.quantity, Math.max(0, room));
        return without.map((line) => (line.key === twin.key ? { ...line, quantity } : line));
      }
      return prev.map((line) =>
        line.key === key ? { ...line, key: nextKey, optionIds: nextIds } : line,
      );
    });
  }

  async function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (busy || waiting) return;
    const q = query.trim();
    if (!q) return;
    let pool = products;
    try {
      const params = new URLSearchParams({ q });
      if (category !== "Todo") params.set("category", category);
      const res = await fetch(`/api/backend/api/cash/grid?${params.toString()}`, { cache: "no-store" });
      if (res.ok) {
        const body = (await res.json()) as { products?: GridProduct[] };
        pool = Array.isArray(body.products) ? body.products : [];
        setProducts(pool);
      }
    } catch {
      return;
    }
    const picked = pickFromGrid(pool, q);
    if (picked.variant) addVariant(picked.variant);
    else if (picked.product) setPicker(picked.product);
    if (picked.variant) setQuery("");
  }

  function openPayModal() {
    if (cart.length === 0 || busy || waiting) return;
    setPayMethod("cash");
    setPayPhase("method");
    setTendered("");
    setError("");
    setHideCashPreview(false);
    setSavedPreview(null);
    setPayOpen(true);
  }

  function closePayModal() {
    if (busy || waiting) return;
    setPayOpen(false);
    setPayPhase("method");
    setTendered("");
    setDiscount("");
    setDiscountPin("");
  }

  function cartPayload() {
    return cart.map((line) => ({
      variant_sku: line.variant_sku,
      quantity: line.quantity,
      options: line.optionIds,
    }));
  }

  function discountFields(): { discount_amount?: string; pin?: string } {
    if (!discountApplied) return {};
    return { discount_amount: discountAmount.toFixed(2), pin: discountPin.trim() };
  }

  async function confirmCashSale() {
    if (!cashConfirmOk || busy || waiting) return;
    setBusy(true);
    setError("");
    setTicketNumber("");
    setTicketPdfHref("");
    try {
      const res = await fetch("/api/backend/api/cash/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          method: "cash",
          lines: cartPayload(),
          ...discountFields(),
        }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo registrar la venta."));
        return;
      }
      const ticket = (await res.json()) as SaleTicketBody;
      const pdfHref = ticket.movement_id ? movementPdfHref(ticket.movement_id) : "";
      setTicketNumber(ticket.number || "");
      setTicketPdfHref(pdfHref);
      const soldLines = linesFromTicket(ticket.lines);
      setSavedPreview({
        ticketNumber: ticket.number || "",
        method: "Efectivo",
        status: "Confirmado",
        lines: soldLines.length > 0 ? soldLines : cartPreviewLines(),
        discount: discountText(ticket.discount_amount) || (discountApplied ? formatBob(discountAmount) : undefined),
        total: ticket.total || formatBob(amountDue),
        currency: ticket.currency || "BOB",
        tendered: Number.isFinite(tenderedAmount) ? formatBob(tenderedAmount) : undefined,
        change: Number.isFinite(changeDue) ? formatBob(Math.max(0, changeDue)) : undefined,
        pdfHref: pdfHref || undefined,
      });
      setCart([]);
      setQuery("");
      setRevision((value) => value + 1);
      setPayOpen(false);
      setPayPhase("method");
      setTendered("");
      setDiscount("");
      setDiscountPin("");
      router.refresh();
    } catch {
      setError("No se pudo registrar la venta.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmQrSale() {
    if (cart.length === 0 || busy || waiting) return;
    setBusy(true);
    setError("");
    setTicketNumber("");
    setTicketPdfHref("");
    try {
      const res = await fetch("/api/backend/api/cash/sales/qr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lines: cartPayload(),
          ...discountFields(),
        }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo emitir el QR."));
        return;
      }
      const ticket = (await res.json()) as QrWaiting;
      if (!ticket.id) {
        setError("No se pudo emitir el QR.");
        return;
      }
      setQrWaiting(ticket);
      setPayPhase("waiting");
      setTendered("");
      // Keep cart visible under the blocking overlay until bank confirm or cancel.
    } catch {
      setError("No se pudo emitir el QR.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelQrPayment() {
    if (!qrWaiting?.id || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(
        `/api/backend/api/cash/sales/${encodeURIComponent(qrWaiting.id)}/cancel`,
        { method: "POST" },
      );
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo cancelar el pago QR."));
        return;
      }
      setQrWaiting(null);
      setPayPhase("method");
      setPayOpen(false);
      setTendered("");
    } catch {
      setError("No se pudo cancelar el pago QR.");
    } finally {
      setBusy(false);
    }
  }

  async function leaveOnTable() {
    const table = tableName.trim();
    if (!table || cart.length === 0 || busy || waiting) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/backend/api/cash/tabs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ table, lines: cartPayload() }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo anotar la mesa."));
        return;
      }
      setCart([]);
      setTableName("");
      setRevision((value) => value + 1);
      router.refresh();
    } catch {
      setError("No se pudo anotar la mesa.");
    } finally {
      setBusy(false);
    }
  }

  function cartPreviewLines(): TicketDrawerLine[] {
    return cart.map((line) => {
      const unit = lineUnit(line, modifiers);
      const priced = Number.isFinite(unit);
      return {
        name: line.name || "Ítem",
        quantity: line.quantity,
        unit: priced ? formatBob(unit) : line.unitPrice,
        total: priced ? formatBob(unit * line.quantity) : "—",
      };
    });
  }

  function openTabPreview(tab: OpenTab) {
    if (payOpen || busy || waiting) return;
    const lines = linesFromTab(tab);
    const currency = tab.items?.find((item) => item.currency)?.currency || "BOB";
    setSavedPreview({
      tableLabel: tab.table_label || "Mesa",
      method: "Sin cobrar",
      status: "Mesa abierta",
      lines,
      total: sumDrawerLines(lines),
      currency,
    });
  }

  async function chargeTab(tabId: string) {
    if (busy || waiting) return;
    const tab = tabs.find((item) => item.id === tabId);
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/cash/tabs/${encodeURIComponent(tabId)}/charge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ method: "cash", ...discountFields() }),
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo cobrar la mesa."));
        return;
      }
      const ticket = (await res.json()) as SaleTicketBody;
      const pdfHref = ticket.movement_id ? movementPdfHref(ticket.movement_id) : "";
      const soldLines = linesFromTicket(ticket.lines);
      const previewLines = soldLines.length > 0 ? soldLines : linesFromTab(tab);
      setTicketNumber(ticket.number || "");
      setTicketPdfHref(pdfHref);
      setSavedPreview({
        ticketNumber: ticket.number || "",
        tableLabel: tab?.table_label || "",
        method: "Efectivo",
        status: "Confirmado",
        lines: previewLines,
        discount: discountText(ticket.discount_amount),
        total: ticket.total || sumDrawerLines(previewLines),
        currency: ticket.currency || "BOB",
        pdfHref: pdfHref || undefined,
      });
      setRevision((value) => value + 1);
      router.refresh();
    } catch {
      setError("No se pudo cobrar la mesa.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelTab(tabId: string) {
    if (busy || waiting) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/backend/api/cash/tabs/${encodeURIComponent(tabId)}/cancel`, {
        method: "POST",
      });
      if (!res.ok) {
        const detail = await readCashDetail(res);
        setError(mapCashError(detail, "No se pudo cancelar la mesa."));
        return;
      }
      setRevision((value) => value + 1);
    } catch {
      setError("No se pudo cancelar la mesa.");
    } finally {
      setBusy(false);
    }
  }

  const posLocked = busy || waiting;
  const showCashDrawer = payOpen && payMethod === "cash" && !waiting && !hideCashPreview;
  const liveCashPreview: TicketDrawerModel = {
    method: "Efectivo",
    status: "Por confirmar",
    lines: cartPreviewLines(),
    discount: discountApplied ? formatBob(discountAmount) : undefined,
    total: formatBob(amountDue),
    currency: cart[0]?.currency || "BOB",
    tendered:
      tendered.trim() && Number.isFinite(tenderedAmount) ? formatBob(tenderedAmount) : undefined,
    change: Number.isFinite(changeDue) ? formatBob(Math.max(0, changeDue)) : undefined,
  };

  return (
    <section className={styles.panel} aria-labelledby="cash-walkin-title">
      <h2 id="cash-walkin-title" className={styles.panelTitle}>
        Venta mostrador
      </h2>
      <p className={styles.panelLead}>
        Tocá un producto para sumarlo. Con varias variantes elegís cuál. El precio lo pone el catálogo.
      </p>

      <div className={styles.posLayout} aria-hidden={waiting || undefined}>
        <div className={styles.posSearch}>
          <label className={styles.searchField}>
            Buscar
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onSearchKeyDown}
              placeholder="Código, nombre o precio"
              autoComplete="off"
              disabled={posLocked}
            />
          </label>
          <div className={styles.categoryRow} role="tablist" aria-label="Categorías">
            <button
              type="button"
              className={category === "Todo" ? styles.categoryChipOn : styles.categoryChip}
              onClick={() => setCategory("Todo")}
              disabled={posLocked}
            >
              Todo
            </button>
            <button
              type="button"
              className={category === "Más vendidos" ? styles.categoryChipOn : styles.categoryChip}
              onClick={() => setCategory("Más vendidos")}
              disabled={posLocked}
            >
              Más vendidos
            </button>
            {categories.map((item) => (
              <button
                key={item.name}
                type="button"
                className={category === item.name ? styles.categoryChipOn : styles.categoryChip}
                onClick={() => setCategory(item.name)}
                disabled={posLocked}
              >
                {item.name}
              </button>
            ))}
          </div>
          {searching ? <p className="meta">Buscando…</p> : null}
          {products.length > 0 ? (
            <ul className={styles.productGrid}>
              {products.map((product) => {
                const blocked = product.sold_out || selectableVariants(product).length === 0;
                return (
                  <li key={product.product_sku}>
                    <button
                      type="button"
                      className={blocked ? styles.gridCardSold : styles.gridCard}
                      disabled={blocked || posLocked}
                      onClick={() => openProduct(product)}
                    >
                      <ProductThumb
                        name={product.name}
                        initial={product.initial}
                        thumbUrl={product.thumb_url}
                        imageUrl={product.image_url}
                        size="fill"
                        className={styles.gridThumb}
                      />
                      <span className={styles.gridName}>{product.name}</span>
                      <span className={styles.gridPrice}>
                        {blocked ? "Agotado" : `${product.price} ${product.currency}`}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : searching ? null : (
            <p className={styles.ticketEmpty}>Nada coincide con esa búsqueda.</p>
          )}
        </div>

        <div className={styles.posTicket}>
          <h3 className={styles.ticketHeading}>Ticket</h3>
          {cart.length === 0 ? (
            <p className={styles.ticketEmpty}>Tocá un producto para armar el ticket.</p>
          ) : (
            <ul className={styles.cartLines}>
              {cart.map((line) => {
                const unit = lineUnit(line, modifiers);
                const lineTotal = Number.isFinite(unit) ? unit * line.quantity : 0;
                const used = skuUsed(cart, line.variant_sku);
                return (
                  <li key={line.key} className={styles.cartLine}>
                    <div className={styles.cartLineMeta}>
                      <span className={styles.cartLineName}>{line.name}</span>
                      <span className={styles.cartLineDetail}>
                        {line.codigo || line.variant_sku} · {formatBob(unit)} {line.currency}
                      </span>
                      {modifiers.length > 0 ? (
                        <span className={styles.categoryRow}>
                          {modifiers.map((modifier) => {
                            const on = line.optionIds.includes(modifier.id);
                            return (
                              <button
                                key={modifier.id}
                                type="button"
                                className={on ? styles.categoryChipOn : styles.categoryChip}
                                disabled={posLocked}
                                onClick={() => toggleOption(line.key, modifier.id)}
                              >
                                {modifier.name} {modifier.price_delta}
                              </button>
                            );
                          })}
                        </span>
                      ) : null}
                    </div>
                    <div className={styles.cartLineControls}>
                      <button
                        type="button"
                        className={styles.qtyButton}
                        aria-label="Quitar uno"
                        disabled={posLocked}
                        onClick={() => setLineQty(line.key, line.quantity - 1)}
                      >
                        −
                      </button>
                      <span className={styles.qtyValue}>{line.quantity}</span>
                      <button
                        type="button"
                        className={styles.qtyButton}
                        aria-label="Agregar uno"
                        disabled={posLocked || used >= line.stock}
                        onClick={() => setLineQty(line.key, line.quantity + 1)}
                      >
                        +
                      </button>
                      <span className={styles.lineTotal}>{formatBob(lineTotal)}</span>
                      <button
                        type="button"
                        className={`secondary ${styles.removeLine}`}
                        disabled={posLocked}
                        onClick={() => removeLine(line.key)}
                      >
                        Quitar
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className={styles.ticketTotals}>
            <div className={styles.totalRow}>
              <span>Subtotal</span>
              <span className={styles.num}>{formatBob(cartTotal)} BOB</span>
            </div>
            <div className={styles.grandTotal}>
              <span>Total</span>
              <span className={styles.grandTotalAmount}>{formatBob(cartTotal)} BOB</span>
            </div>
          </div>

          <button
            type="button"
            className={styles.chargeButton}
            disabled={cart.length === 0 || posLocked}
            onClick={openPayModal}
          >
            Cobrar
          </button>

          <div className={styles.openTabs}>
            <label className={styles.searchField}>
              Mesa
              <input
                value={tableName}
                onChange={(event) => setTableName(event.target.value)}
                placeholder="Mesa 4"
                disabled={posLocked}
              />
            </label>
            <button
              type="button"
              className="secondary"
              disabled={posLocked || cart.length === 0 || !tableName.trim()}
              onClick={() => void leaveOnTable()}
            >
              Dejar en la mesa
            </button>
            <h3 className={styles.ticketHeading}>Mesas abiertas</h3>
            {tabs.length === 0 ? (
              <p className={styles.ticketEmpty}>No hay mesas esperando el cobro.</p>
            ) : (
              <ul className={styles.cartLines}>
                {tabs.map((tab) => (
                  <li key={tab.id} className={styles.tabRow}>
                    <button
                      type="button"
                      className={styles.tabPreviewButton}
                      disabled={posLocked}
                      onClick={() => openTabPreview(tab)}
                    >
                      <strong>{tab.table_label || "Mesa"}</strong>
                      <span className={styles.cartLineDetail}>
                        {(tab.items || [])
                          .map((item) => `${item.quantity || 1}× ${item.name || "Ítem"}`)
                          .join(", ") || "Sin ítems"}
                      </span>
                    </button>
                    <span className={styles.cartLineControls}>
                      <button
                        type="button"
                        disabled={posLocked}
                        onClick={() => void chargeTab(tab.id)}
                      >
                        Cobrar
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={posLocked}
                        onClick={() => void cancelTab(tab.id)}
                      >
                        Cancelar
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {ticketNumber ? (
        <p className={styles.ticketOk}>
          Ticket <strong>{ticketNumber}</strong> registrado.
          {ticketPdfHref ? (
            <>
              {" "}
              <a href={ticketPdfHref} target="_blank" rel="noopener noreferrer">
                Descargar ticket
              </a>
            </>
          ) : null}
        </p>
      ) : null}
      {error && !payOpen ? <p className="error">{error}</p> : null}

      {picker ? (
        <div
          className={styles.payModalBackdrop}
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) setPicker(null);
          }}
        >
          <div className={styles.payModal} role="dialog" aria-modal="true" aria-labelledby="cash-variant-title">
            <h3 id="cash-variant-title" className={styles.panelTitle}>
              {picker.name}
            </h3>
            <p className={styles.panelLead}>Elegí la variante.</p>
            <ul className={styles.cartLines}>
              {picker.variants.map((variant) => {
                const blocked = variant.sold_out || variant.selectable === false || variant.stock < 1;
                const detail = [variant.talla, variant.color].filter(Boolean).join(" · ");
                return (
                  <li key={variant.variant_sku}>
                    <button
                      type="button"
                      className={blocked ? styles.gridCardSold : styles.gridCard}
                      disabled={blocked || posLocked}
                      onClick={() => addVariant(variant)}
                    >
                      <span className={styles.gridName}>{detail || variant.variant_sku}</span>
                      <span className={styles.gridPrice}>
                        {blocked ? "Agotado" : `${variant.price} ${variant.currency}`}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <button type="button" className="secondary" onClick={() => setPicker(null)}>
              Cerrar
            </button>
          </div>
        </div>
      ) : null}

      {payOpen ? (
        <div
          className={showCashDrawer ? styles.payWithPreview : styles.payModalBackdrop}
          role="presentation"
          onClick={(event) => {
            if (waiting) return;
            if (event.target === event.currentTarget) closePayModal();
          }}
        >
          {showCashDrawer ? (
            <button
              type="button"
              className={styles.payWithPreviewBackdrop}
              aria-label="Cerrar cobro"
              onClick={closePayModal}
            />
          ) : null}
          <div
            className={waiting ? styles.payModalWaiting : styles.payModal}
            role="dialog"
            aria-modal={waiting || !showCashDrawer}
            aria-labelledby={waiting ? "cash-qr-wait-title" : "cash-pay-title"}
          >
            {waiting && qrWaiting ? (
              <>
                <h3 id="cash-qr-wait-title" className={styles.panelTitle}>
                  Esperando pago QR
                </h3>
                <p className={styles.payModalTotal}>
                  Ticket <strong>{qrWaiting.number || "—"}</strong>
                </p>
                <p className={styles.panelLead}>
                  Mostrá el QR al cliente. El stock se descuenta cuando el banco confirma; no suma
                  al efectivo del turno.
                </p>
                <ul className={styles.qrWaitLines}>
                  {waitingLines.map((line, index) => (
                    <li key={`${line.variant_sku || "line"}-${index}`}>
                      <span>
                        {(line.quantity ?? 1) > 1 ? `${line.quantity}× ` : ""}
                        {line.name || line.variant_sku || "Ítem"}
                      </span>
                      <span className={styles.num}>
                        {line.line_total || line.unit_price || "—"} {line.currency || waitingCurrency}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className={styles.payModalTotal}>
                  Total{" "}
                  <strong>
                    {waitingTotal} {waitingCurrency}
                  </strong>
                </p>
                {qrWaiting.provider_ref ? (
                  <p className={styles.qrRef}>
                    Ref: <code>{qrWaiting.provider_ref}</code>
                  </p>
                ) : null}
                {waitingQrSrc ? (
                  <img
                    className={styles.qrWaitImage}
                    src={waitingQrSrc}
                    alt="QR de pago"
                  />
                ) : qrWaiting.qr ? (
                  <div className={styles.qrCodePanel} aria-label="Código de pago">
                    <code>{qrWaiting.qr}</code>
                  </div>
                ) : (
                  <p className="meta">QR sin imagen en esta emisión.</p>
                )}
                <p className={styles.qrWaitHint}>Esperando confirmación del banco…</p>
                {error ? <p className="error">{error}</p> : null}
                <div className={styles.payModalActions}>
                  <button type="button" className="secondary" disabled={busy} onClick={cancelQrPayment}>
                    {busy ? "…" : "Cancelar pago"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3 id="cash-pay-title" className={styles.panelTitle}>
                  Cobrar ticket
                </h3>
                <p className={styles.payModalTotal}>
                  Total <strong>{formatBob(amountDue)} BOB</strong>
                </p>
                <label className={styles.searchField}>
                  Descuento
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.01"
                    min="0"
                    value={discount}
                    onChange={(event) => setDiscount(event.target.value)}
                    placeholder="0.00"
                    disabled={busy}
                  />
                </label>
                {discountApplied ? (
                  <label className={styles.searchField}>
                    PIN del supervisor
                    <input
                      type="password"
                      inputMode="numeric"
                      value={discountPin}
                      onChange={(event) => setDiscountPin(event.target.value)}
                      autoComplete="off"
                      disabled={busy}
                    />
                  </label>
                ) : null}

                <div className={styles.payMethodTabs} role="tablist" aria-label="Método de cobro">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={payMethod === "cash"}
                    className={payMethod === "cash" ? styles.payMethodSelected : styles.payMethod}
                    disabled={busy}
                    onClick={() => {
                      setPayMethod("cash");
                      setHideCashPreview(false);
                    }}
                  >
                    Efectivo
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={payMethod === "qr"}
                    className={payMethod === "qr" ? styles.payMethodSelected : styles.payMethod}
                    disabled={busy}
                    onClick={() => setPayMethod("qr")}
                  >
                    QR
                  </button>
                </div>

                {payMethod === "cash" ? (
                  <div className={styles.payCashBody}>
                    <label className={styles.searchField}>
                      Entrega
                      <input
                        type="number"
                        inputMode="decimal"
                        step="0.01"
                        min="0"
                        value={tendered}
                        onChange={(event) => setTendered(event.target.value)}
                        placeholder={formatBob(amountDue)}
                        autoFocus
                        disabled={busy}
                      />
                    </label>
                    <p className={styles.changeRow}>
                      Vuelto{" "}
                      <strong className={styles.num}>
                        {Number.isFinite(changeDue) ? formatBob(Math.max(0, changeDue)) : "—"} BOB
                      </strong>
                    </p>
                    {Number.isFinite(tenderedAmount) && tenderedAmount + 1e-9 < amountDue ? (
                      <p className="error">El monto entregado es menor al total.</p>
                    ) : null}
                  </div>
                ) : (
                  <p className={styles.panelLead}>
                    Se emite un QR por el total del ticket. El stock se descuenta cuando Cobros
                    confirma el pago.
                  </p>
                )}

                {error ? <p className="error">{error}</p> : null}

                <div className={styles.payModalActions}>
                  <button type="button" className="secondary" disabled={busy} onClick={closePayModal}>
                    Cancelar
                  </button>
                  {payMethod === "cash" ? (
                    <button type="button" disabled={!cashConfirmOk || busy} onClick={confirmCashSale}>
                      {busy ? "…" : "Confirmar efectivo"}
                    </button>
                  ) : (
                    <button type="button" disabled={busy || cart.length === 0} onClick={confirmQrSale}>
                      {busy ? "…" : "Emitir QR"}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
          {showCashDrawer ? (
            <TicketDrawer embedded model={liveCashPreview} onClose={() => setHideCashPreview(true)} />
          ) : null}
        </div>
      ) : null}

      {savedPreview && !payOpen ? (
        <TicketDrawer model={savedPreview} onClose={() => setSavedPreview(null)} />
      ) : null}
    </section>
  );
}
