import { JournalLegend } from "./journal-view";
import styles from "./ledger.module.css";

export type BankReconLine = {
  entry_id: string;
  entry_at?: string | null;
  direction: string;
  amount: string;
  currency?: string;
  memo?: string;
  matched: boolean;
};

export type BankReconPayment = {
  payment_id: string;
  created_at?: string | null;
  amount: string;
  currency?: string;
  provider?: string;
  matched: boolean;
};

export type BankReconMatch = {
  entry_id: string;
  payment_id: string;
  amount: string;
  day?: string | null;
};

export type BankRecon = {
  bank_lines: BankReconLine[];
  payments: BankReconPayment[];
  matches: BankReconMatch[];
};

function journalSide(direction: string): string {
  if (direction === "debit") return "Debe";
  if (direction === "credit") return "Haber";
  return direction;
}

export function BankReconView({ data }: { data: BankRecon }) {
  return (
    <>
      <JournalLegend />
      <p className="meta" role="note">
        Conciliación liviana: movimientos de Banco frente a pagos confirmados (mismo monto ±0.01 y
        día UTC).
      </p>
      <p className={styles.balanceSummary}>
        <span>
          Líneas banco: <strong>{(data.bank_lines || []).length}</strong>
        </span>
        <span className={styles.journalEntrySep} aria-hidden>
          ·
        </span>
        <span>
          Pagos: <strong>{(data.payments || []).length}</strong>
        </span>
        <span className={styles.journalEntrySep} aria-hidden>
          ·
        </span>
        <span>
          Coincidencias: <strong>{(data.matches || []).length}</strong>
        </span>
      </p>

      <h2 className={styles.breakdownTitle}>Cuenta Banco (diario)</h2>
      <div className="table-scroll">
        <table className={styles.ledgerTable}>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Debe / Haber</th>
              <th className={styles.numCol}>Monto</th>
              <th>Memo</th>
              <th>Coincide</th>
            </tr>
          </thead>
          <tbody>
            {(data.bank_lines || []).length === 0 ? (
              <tr>
                <td colSpan={5}>Sin movimientos de Banco en el período.</td>
              </tr>
            ) : (
              data.bank_lines.map((line) => (
                <tr key={`${line.entry_id}-${line.amount}-${line.direction}`}>
                  <td>{(line.entry_at || "").slice(0, 16).replace("T", " ") || "—"}</td>
                  <td>{journalSide(line.direction)}</td>
                  <td className={styles.numCol}>
                    {line.amount} {line.currency || "BOB"}
                  </td>
                  <td className={styles.mutedCell}>{line.memo || "—"}</td>
                  <td>{line.matched ? "Sí" : "No"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <h2 className={styles.breakdownTitle}>Pagos confirmados</h2>
      <div className="table-scroll">
        <table className={styles.ledgerTable}>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Proveedor</th>
              <th className={styles.numCol}>Monto</th>
              <th>Coincide</th>
            </tr>
          </thead>
          <tbody>
            {(data.payments || []).length === 0 ? (
              <tr>
                <td colSpan={4}>Sin pagos confirmados no efectivo en el período.</td>
              </tr>
            ) : (
              data.payments.map((pay) => (
                <tr key={pay.payment_id}>
                  <td>{(pay.created_at || "").slice(0, 16).replace("T", " ") || "—"}</td>
                  <td>{pay.provider || "—"}</td>
                  <td className={styles.numCol}>
                    {pay.amount} {pay.currency || "BOB"}
                  </td>
                  <td>{pay.matched ? "Sí" : "No"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}