import { JournalView, type JournalEntry } from "./journal-view";
import styles from "./ledger.module.css";

const ORIGIN_LABEL: Record<string, string> = {
  cash: "Caja",
  payment: "Pago confirmado",
  purchase: "Compra",
  cogs: "Costo de ventas",
  supplier_payment: "Pago a proveedor",
  adjustment: "Ajuste manual",
};

const GROUP_ORDER = [
  "cash",
  "payment",
  "purchase",
  "cogs",
  "supplier_payment",
  "adjustment",
] as const;

function sumEntriesSide(entries: JournalEntry[], side: "debit" | "credit"): string {
  let total = 0;
  let currency = "BOB";
  let hasAmount = false;
  for (const entry of entries) {
    for (const line of entry.lines) {
      const isDebit = line.direction === "debit";
      if ((side === "debit" && isDebit) || (side === "credit" && !isDebit)) {
        const parsed = Number.parseFloat(line.amount);
        if (Number.isFinite(parsed) && parsed !== 0) {
          total += parsed;
          hasAmount = true;
        }
        if (line.currency) currency = line.currency;
      }
    }
  }
  if (!hasAmount) return "—";
  const rounded = Math.round(total * 100) / 100;
  return `${rounded} ${currency}`;
}

function groupOrderIndex(source: string): number {
  const idx = GROUP_ORDER.indexOf(source as (typeof GROUP_ORDER)[number]);
  return idx === -1 ? GROUP_ORDER.length + 1 : idx;
}

function groupByOrigin(entries: JournalEntry[]): Map<string, JournalEntry[]> {
  const map = new Map<string, JournalEntry[]>();
  for (const entry of entries) {
    const key = entry.origin_source || "other";
    const bucket = map.get(key) || [];
    bucket.push(entry);
    map.set(key, bucket);
  }
  for (const bucket of map.values()) {
    bucket.sort((a, b) => {
      const ta = a.entry_at || "";
      const tb = b.entry_at || "";
      return tb.localeCompare(ta);
    });
  }
  return map;
}

/** Soften a few internal memos for owner-facing Resumen (display only). */
function humanizeEntry(entry: JournalEntry): JournalEntry {
  const raw = (entry.memo || "").trim().toLowerCase();
  let memo = entry.memo;
  if (raw === "caja in venta" || raw.startsWith("caja in ")) {
    memo = "Venta en Caja";
  } else if (raw.startsWith("caja out ")) {
    memo = "Salida de Caja";
  } else if (raw.startsWith("cogs sale")) {
    memo = "Costo de la venta";
  } else if (raw.startsWith("reverso cogs")) {
    memo = "Reverso del costo de venta";
  }
  return memo === entry.memo ? entry : { ...entry, memo };
}

export function OwnerSummaryView({ entries }: { entries: JournalEntry[] }) {
  if (entries.length === 0) {
    return <p className="meta">Todavía no hay asientos en este período.</p>;
  }

  const grouped = groupByOrigin(entries);
  const sources = [...grouped.keys()].sort((a, b) => {
    const orderDiff = groupOrderIndex(a) - groupOrderIndex(b);
    if (orderDiff !== 0) return orderDiff;
    const labelA = ORIGIN_LABEL[a] || a;
    const labelB = ORIGIN_LABEL[b] || b;
    return labelA.localeCompare(labelB, "es");
  });

  return (
    <div className={styles.summaryWrap}>
      <p className={styles.summaryNote} role="note">
        El <strong>Resumen</strong> es la vista simple del dueño sobre el mismo Libro Diario: agrupa
        por origen (Caja, pagos, compras…). El chip <strong>Diario</strong> muestra el libro
        completo, asiento por asiento. Los otros libros (Mayor, Balance, etc.) son vistas aparte.
      </p>
      <div className={styles.summaryGroups}>
        {sources.map((source) => {
          const groupEntries = (grouped.get(source) || []).map(humanizeEntry);
          const title = ORIGIN_LABEL[source] || source;
          const totalDebit = sumEntriesSide(groupEntries, "debit");
          const totalCredit = sumEntriesSide(groupEntries, "credit");
          const countLabel =
            groupEntries.length === 1 ? "1 asiento" : `${groupEntries.length} asientos`;

          return (
            <section
              key={source}
              className={styles.summaryGroup}
              aria-label={`Resumen ${title}`}
            >
              <header className={styles.summaryGroupHeader}>
                <div className={styles.summaryGroupTitleRow}>
                  <h2 className={styles.summaryGroupTitle}>{title}</h2>
                  <span className={styles.summaryGroupCount}>{countLabel}</span>
                </div>
                <div className={styles.summaryGroupTotals} aria-label={`Totales ${title}`}>
                  <span>
                    Total <strong>Debe</strong> {totalDebit}
                  </span>
                  <span className={styles.summaryGroupTotalsSep} aria-hidden>
                    ·
                  </span>
                  <span>
                    Total <strong>Haber</strong> {totalCredit}
                  </span>
                </div>
              </header>
              <div className={styles.summaryBookBody}>
                <JournalView entries={groupEntries} />
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
