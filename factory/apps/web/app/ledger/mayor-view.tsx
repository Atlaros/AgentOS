import { JournalLegend } from "./journal-view";
import styles from "./ledger.module.css";

export type MayorLine = {
  entry_at?: string | null;
  entry_id: string;
  kind: string;
  memo?: string;
  debit: string;
  credit: string;
  balance: string;
};

export type MayorAccount = {
  code: string;
  name: string;
  opening?: string;
  lines: MayorLine[];
  closing_balance: string;
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

function moneyOrDash(value: string): string {
  if (!value || value === "0") return "—";
  return value;
}

/** Display-only memo softening (same patterns as Resumen dueño). */
function humanizeMemo(memo?: string): string | undefined {
  const raw = (memo || "").trim().toLowerCase();
  if (!raw) return undefined;
  if (raw === "caja in venta" || raw.startsWith("caja in ")) return "Venta en Caja";
  if (raw.startsWith("caja out ")) return "Salida de Caja";
  if (raw.startsWith("cogs sale")) return "Costo de la venta";
  if (raw.startsWith("reverso cogs")) return "Reverso del costo de venta";
  return memo?.trim() || undefined;
}

function lineConcept(line: MayorLine): string {
  const kindLabel = line.kind === "post" ? undefined : KIND[line.kind] || line.kind;
  const memo = humanizeMemo(line.memo);
  if (kindLabel && memo) return `${kindLabel} · ${memo}`;
  if (memo) return memo;
  if (kindLabel) return kindLabel;
  return "—";
}

function sumMovement(lines: MayorLine[], side: "debit" | "credit"): string {
  let total = 0;
  let has = false;
  for (const line of lines) {
    const raw = side === "debit" ? line.debit : line.credit;
    const n = Number.parseFloat(raw);
    if (Number.isFinite(n) && n !== 0) {
      total += n;
      has = true;
    }
  }
  if (!has) return "—";
  const rounded = Math.round(total * 100) / 100;
  return String(rounded);
}

export function MayorView({
  accounts,
  selectedAccount,
}: {
  accounts: MayorAccount[];
  selectedAccount?: string;
}) {
  if (accounts.length === 0) {
    return (
      <p className="meta">
        {selectedAccount
          ? `Sin movimientos en la cuenta ${selectedAccount} para este período.`
          : "Todavía no hay movimientos en el mayor para este período."}
      </p>
    );
  }

  return (
    <div className={styles.mayorStack}>
      <p className={styles.summaryNote} role="note">
        El <strong>Mayor</strong> muestra los movimientos de cada cuenta en el período.{" "}
        <strong>Debe</strong> y <strong>Haber</strong> significan lo mismo que en el Diario.
      </p>
      <JournalLegend />
      {accounts.map((account) => (
        <section
          key={account.code}
          className={styles.bookCard}
          aria-label={`Mayor ${account.code}`}
        >
          <header className={styles.bookCardHeader}>
            <h2 className={styles.bookCardTitle}>
              <span className={styles.accountCode}>{account.code}</span> {account.name}
            </h2>
            <div className={styles.bookCardMeta} aria-label="Saldos de la cuenta">
              {account.opening != null ? (
                <span>
                  Apertura <strong>{account.opening} BOB</strong>
                </span>
              ) : null}
              <span>
                Cierre <strong>{account.closing_balance} BOB</strong>
              </span>
            </div>
          </header>
          <div className="table-scroll">
            <table className={styles.ledgerTable}>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Concepto</th>
                  <th className={styles.numCol}>Debe</th>
                  <th className={styles.numCol}>Haber</th>
                  <th className={styles.numCol}>Saldo</th>
                </tr>
              </thead>
              <tbody>
                {account.lines.length === 0 ? (
                  <tr>
                    <td colSpan={5}>Sin líneas.</td>
                  </tr>
                ) : (
                  account.lines.map((line) => (
                    <tr
                      key={`${line.entry_id}-${line.debit}-${line.credit}-${line.balance}`}
                      className={line.kind === "reverse" ? styles.statusVoided : undefined}
                    >
                      <td>{formatWhen(line.entry_at)}</td>
                      <td className={styles.mutedCell}>{lineConcept(line)}</td>
                      <td className={styles.numCol}>{moneyOrDash(line.debit)}</td>
                      <td className={styles.numCol}>{moneyOrDash(line.credit)}</td>
                      <td className={styles.numCol}>{line.balance}</td>
                    </tr>
                  ))
                )}
              </tbody>
              {account.lines.length > 0 ? (
                <tfoot>
                  <tr className={styles.totalsRow}>
                    <td colSpan={2}>Movimiento del período</td>
                    <td className={styles.numCol}>{sumMovement(account.lines, "debit")}</td>
                    <td className={styles.numCol}>{sumMovement(account.lines, "credit")}</td>
                    <td className={styles.numCol} aria-hidden>
                      —
                    </td>
                  </tr>
                </tfoot>
              ) : null}
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}