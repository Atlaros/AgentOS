import { JournalLegend } from "./journal-view";
import styles from "./ledger.module.css";

export type IncomeStatement = {
  revenue: string;
  cogs?: string;
  expenses: string;
  draws: string;
  result: string;
  currency?: string;
  note?: string;
};

const INCOME_ROWS: { key: keyof IncomeStatement; label: string }[] = [
  { key: "revenue", label: "Ingresos (ventas)" },
  { key: "cogs", label: "Costo de ventas" },
  { key: "expenses", label: "Gastos" },
  { key: "draws", label: "Retiros del dueño" },
  { key: "result", label: "Resultado gerencial" },
];

export function IncomeView({ data }: { data: IncomeStatement }) {
  const currency = data.currency || "BOB";

  return (
    <>
      <JournalLegend />
      <p className="meta" role="note">
        {data.note || "Incluye COGS cuando el costo de compra es conocido; utilidad gerencial."}
      </p>
      <div className="table-scroll">
        <table className={styles.ledgerTable}>
          <thead>
            <tr>
              <th>Concepto</th>
              <th className={styles.numCol}>Monto</th>
            </tr>
          </thead>
          <tbody>
            {INCOME_ROWS.map(({ key, label }) => {
              const raw = data[key];
              const amount =
                key === "cogs" ? data.cogs || "0" : typeof raw === "string" ? raw : "0";
              const isResult = key === "result";
              return (
                <tr key={key} className={isResult ? styles.totalsRow : undefined}>
                  <td>{label}</td>
                  <td className={styles.numCol}>
                    {amount} {currency}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}