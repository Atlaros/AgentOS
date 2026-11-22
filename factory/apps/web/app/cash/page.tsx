import { Suspense } from "react";

import { apiGet } from "@/lib/api";

import type { CashFilterValues } from "./cash-filters";
import { CashWorkspace } from "./cash-workspace";
import type { CashActivityEntry, CashMovement } from "./movements-table";
import type { CashSession } from "./session-panel";

type CashBook = {
  in: string;
  out: string;
  balance: string;
  count: number;
  note: string;
  session: CashSession | null;
  movements: CashMovement[];
  entries?: CashActivityEntry[];
};

type CashHistory = {
  closes: CashSession[];
};

type CashPageProps = {
  searchParams: Promise<{
    tab?: string | string[];
    direction?: string | string[];
    category?: string | string[];
    method?: string | string[];
    status?: string | string[];
    user?: string | string[];
    from?: string | string[];
    to?: string | string[];
    session_id?: string | string[];
  }>;
};

function readQuery(value: string | string[] | undefined): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return (raw || "").trim();
}

function filtersFromParams(params: Awaited<CashPageProps["searchParams"]>): CashFilterValues {
  return {
    direction: readQuery(params.direction),
    category: readQuery(params.category),
    method: readQuery(params.method),
    status: readQuery(params.status),
    user: readQuery(params.user),
    from: readQuery(params.from),
    to: readQuery(params.to),
    session_id: readQuery(params.session_id),
  };
}

function cashQueryString(filters: CashFilterValues): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value);
  }
  return params.toString();
}

function entriesFromBook(book: CashBook | null): CashActivityEntry[] {
  if (!book) return [];
  if (Array.isArray(book.entries)) {
    return book.entries;
  }
  // Fallback if an older API omits entries: map cash movements only.
  return (book.movements || []).map((movement) => ({
    id: movement.id,
    kind: "cash_movement",
    created_at: movement.created_at,
    direction: movement.direction,
    amount: movement.amount,
    currency: movement.currency,
    category: movement.category,
    method: movement.method || "cash",
    status: movement.status,
    affects_cash: true,
    reason: movement.reason,
    summary: "",
    recorded_by_name: movement.recorded_by_name,
    ticket_id: movement.ticket_id,
    ticket_number: null,
    session_id: null,
    movement_id: movement.id,
    void_reason: movement.void_reason,
  }));
}

function sessionsForSelector(
  session: CashSession | null,
  closes: CashSession[],
): CashSession[] {
  const byId = new Map<string, CashSession>();
  if (session?.id) byId.set(session.id, session);
  for (const item of closes) {
    if (item?.id && !byId.has(item.id)) byId.set(item.id, item);
  }
  return Array.from(byId.values());
}

export default async function CashPage({ searchParams }: CashPageProps) {
  const params = await searchParams;
  const filters = filtersFromParams(params);
  const query = cashQueryString(filters);

  let book: CashBook | null = null;
  let closes: CashSession[] = [];
  let error = "";

  try {
    book = await apiGet<CashBook>(query ? `/api/cash?${query}` : "/api/cash");
  } catch (err) {
    error = err instanceof Error ? err.message : "error";
  }
  try {
    const historyResult = await apiGet<CashHistory>("/api/cash/session/history");
    closes = historyResult.closes || [];
  } catch {
    closes = [];
  }

  const session = book?.session ?? null;
  const open = session?.status === "open";
  const opening = open && session ? session.opening_float : "—";
  const cashIn = open && session ? session.in || "0.00" : "—";
  const cashOut = open && session ? session.out || "0.00" : "—";
  const expected = open && session ? session.expected_cash : "—";
  const qrIn =
    open && session?.qr_in && Number(String(session.qr_in).replace(",", ".")) > 0
      ? session.qr_in
      : null;
  const entries = entriesFromBook(book);
  const sessions = sessionsForSelector(session, closes);

  return (
    <>
      <h1>Caja</h1>
      <p className="lead">
        Efectivo físico por turno. El QR Baneco lo confirma Cobros; Contabilidad consolida.
      </p>
      {error ? <p className="error">{error}</p> : null}
      <Suspense fallback={<p className="meta">Cargando caja…</p>}>
        <CashWorkspace
          filters={filters}
          session={session}
          open={open}
          opening={opening}
          cashIn={cashIn}
          cashOut={cashOut}
          expected={expected}
          qrIn={qrIn}
          entries={entries}
          count={entries.length}
          note={book?.note}
          closes={closes}
          sessions={sessions}
        />
      </Suspense>
    </>
  );
}
