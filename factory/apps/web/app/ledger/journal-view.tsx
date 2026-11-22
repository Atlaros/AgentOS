import Link from "next/link";

import styles from "./ledger.module.css";

export type JournalLine = {
  account_code: string;
  account_name: string;
  direction: string;
  amount: string;
  currency: string;
};

export type JournalEntry = {
  id: string;
  entry_at?: string | null;
  origin_source: string;
  origin_id: string;
  kind: string;
  memo?: string;
  origin_href?: string | null;
  lines: JournalLine[];
};

const ORIGIN: Record<string, string> = {
  payment: "Pago confirmado",
  cash: "Caja",
  purchase: "Compra",
  adjustment: "Ajuste manual",
};

const KIND: Record<string, string> = {
  post: "Asiento",
  reverse: "Reverso",
};

function formatWhen(raw: string | null | undefined): string {
  if (!raw) return "—";
  const stamp = raw.slice(0, 16).replace("T", " ");
  return stamp || raw;
}

function formatAmount(line: JournalLine, side: "debit" | "credit"): string {
  const isDebit = line.direction === "debit";
  if (side === "debit" && isDebit) {
    return `${line.amount} ${line.currency}`;
  }
  if (side === "credit" && !isDebit) {
    return `${line.amount} ${line.currency}`;
  }
  return "—";
}

function sumSide(lines: JournalLine[], side: "debit" | "credit"): string {
  let total = 0;
  let currency = "BOB";
  for (const line of lines) {
    const isDebit = line.direction === "debit";
    if ((side === "debit" && isDebit) || (side === "credit" && !isDebit)) {
      const parsed = Number.parseFloat(line.amount);
      if (Number.isFinite(parsed)) total += parsed;
      if (line.currency) currency = line.currency;
    }
  }
  if (total === 0) return "—";
  const rounded = Math.round(total * 100) / 100;
  return `${rounded} ${currency}`;
}

export function JournalLegend() {
  return (
    <p className={styles.debeHaberLegend} role="note">
      <strong>Debe</strong> = valor que entra a esa cuenta · <strong>Haber</strong> = valor que sale o
      se registra del otro lado del asiento.
    </p>
  );
}

export function JournalView({ entries }: { entries: JournalEntry[] }) {
  if (entries.length === 0) {
    return <p className="meta">Todavía no hay asientos en este período.</p>;
  }

  return (
    <div className={styles.journalBook}>
      {entries.map((entry) => {
        const originLabel = ORIGIN[entry.origin_source] || entry.origin_source;
        const kindLabel = KIND[entry.kind] || entry.kind;
        return (
          <article
            key={entry.id}
            className={`${styles.journalEntry}${entry.kind === "reverse" ? ` ${styles.statusVoided}` : ""}`}
            aria-label={`Asiento ${formatWhen(entry.entry_at)}`}
          >
            <header className={styles.journalEntryHeader}>
              <span>{formatWhen(entry.entry_at)}</span>
              <span className={styles.journalEntrySep} aria-hidden>
                ·
              </span>
              <span>
                {entry.origin_href ? (
                  <Link className={styles.refLink} href={entry.origin_href}>
                    {originLabel}
                  </Link>
                ) : (
                  originLabel
                )}
              </span>
              <span className={styles.journalEntrySep} aria-hidden>
                ·
              </span>
              <span>{kindLabel}</span>
              {entry.memo ? (
                <>
                  <span className={styles.journalEntrySep} aria-hidden>
                    ·
                  </span>
                  <span className={styles.mutedCell}>{entry.memo}</span>
                </>
              ) : null}
            </header>
            <div className="table-scroll">
              <table className={styles.ledgerTable}>
                <thead>
                  <tr>
                    <th>Cuenta</th>
                    <th className={styles.numCol}>Debe</th>
                    <th className={styles.numCol}>Haber</th>
                  </tr>
                </thead>
                <tbody>
                  {entry.lines.map((line, index) => (
                    <tr key={`${entry.id}-${index}`}>
                      <td>
                        <span className={styles.accountCode}>{line.account_code}</span>{" "}
                        {line.account_name}
                      </td>
                      <td className={styles.numCol}>{formatAmount(line, "debit")}</td>
                      <td className={styles.numCol}>{formatAmount(line, "credit")}</td>
                    </tr>
                  ))}
                  <tr className={styles.totalsRow}>
                    <td>Total del asiento</td>
                    <td className={styles.numCol}>{sumSide(entry.lines, "debit")}</td>
                    <td className={styles.numCol}>{sumSide(entry.lines, "credit")}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        );
      })}
    </div>
  );
}