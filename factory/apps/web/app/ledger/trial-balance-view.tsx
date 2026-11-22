import { JournalLegend } from "./journal-view";
import styles from "./ledger.module.css";

export type TrialBalanceRow = {
  code: string;
  name: string;
  debit: string;
  credit: string;
};

export type TrialBalance = {
  rows: TrialBalanceRow[];
  total_debit: string;
  total_credit: string;
  balanced: boolean;
};

function moneyOrDash(value: string): string {
  if (!value || value === "0") return "—";
  return value;
}

export function TrialBalanceView({ data }: { data: TrialBalance }) {
  return (
    <>
      <JournalLegend />
      <p className={styles.balanceBadgeRow}>
        <span
          className={`${styles.balanceBadge}${
            data.balanced ? ` ${styles.balanceBadgeOk}` : ` ${styles.balanceBadgeBad}`
          }`}
        >
          {data.balanced ? "Cuadra" : "No cuadra"}
        </span>
        <span className="meta">
          Totales Debe {data.total_debit} · Haber {data.total_credit} BOB
        </span>
      </p>
      <div className="table-scroll">
        <table className={styles.ledgerTable}>
          <thead>
            <tr>
              <th>Código</th>
              <th>Cuenta</th>
              <th className={styles.numCol}>Debe</th>
              <th className={styles.numCol}>Haber</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 ? (
              <tr>
                <td colSpan={4}>Todavía no hay saldos en este período.</td>
              </tr>
            ) : (
              data.rows.map((row) => (
                <tr key={row.code}>
                  <td className={styles.accountCode}>{row.code}</td>
                  <td>{row.name}</td>
                  <td className={styles.numCol}>{moneyOrDash(row.debit)}</td>
                  <td className={styles.numCol}>{moneyOrDash(row.credit)}</td>
                </tr>
              ))
            )}
            <tr className={styles.totalsRow}>
              <td colSpan={2}>Total</td>
              <td className={styles.numCol}>{data.total_debit}</td>
              <td className={styles.numCol}>{data.total_credit}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}