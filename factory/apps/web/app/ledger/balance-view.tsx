import styles from "./ledger.module.css";

export type BalanceRow = {
  code: string;
  name: string;
  account_type: string;
  balance: string;
};

export type BalanceSheet = {
  assets: string;
  liabilities: string;
  equity: string;
  equity_draws: string;
  net_income?: string;
  balanced_check: boolean;
  rows: BalanceRow[];
};

const ASSET_TYPES = new Set(["asset"]);
const LIABILITY_EQUITY_TYPES = new Set(["liability", "equity", "equity_draw", "income", "expense"]);

function groupRows(rows: BalanceRow[]) {
  const assets: BalanceRow[] = [];
  const liabilities: BalanceRow[] = [];
  for (const row of rows) {
    if (ASSET_TYPES.has(row.account_type)) {
      assets.push(row);
    } else if (LIABILITY_EQUITY_TYPES.has(row.account_type)) {
      liabilities.push(row);
    } else {
      assets.push(row);
    }
  }
  return { assets, liabilities };
}

function sumRowBalances(rows: BalanceRow[]): string {
  let total = 0;
  let has = false;
  for (const row of rows) {
    const n = Number.parseFloat(row.balance);
    if (Number.isFinite(n)) {
      total += n;
      has = true;
    }
  }
  if (!has) return "—";
  const rounded = Math.round(total * 100) / 100;
  return `${rounded} BOB`;
}

function BalanceLegend() {
  return (
    <p className={styles.balanceLegend} role="note">
      <strong>Activo</strong> = lo que el negocio tiene; <strong>Pasivo</strong> = lo que debe;{" "}
      <strong>Patrimonio</strong> = capital y resultados del dueño. En un balance sano, activos
      cuadran con pasivos más patrimonio.
    </p>
  );
}

function BalancePanel({
  title,
  rows,
  totalLabel,
}: {
  title: string;
  rows: BalanceRow[];
  totalLabel: string;
}) {
  return (
    <section className={styles.bookCard} aria-label={title}>
      <header className={styles.bookCardHeader}>
        <h2 className={styles.bookCardTitle}>{title}</h2>
      </header>
      {rows.length === 0 ? (
        <p className={styles.bookCardEmpty}>Sin cuentas con saldo en este lado.</p>
      ) : (
        <div className="table-scroll">
          <table className={styles.ledgerTable}>
            <thead>
              <tr>
                <th>Cuenta</th>
                <th className={styles.numCol}>Saldo</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <td>
                    <span className={styles.accountCode}>{row.code}</span> {row.name}
                  </td>
                  <td className={styles.numCol}>{row.balance} BOB</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className={styles.totalsRow}>
                <td>{totalLabel}</td>
                <td className={styles.numCol}>{sumRowBalances(rows)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}

export function BalanceView({ data }: { data: BalanceSheet }) {
  const { assets, liabilities } = groupRows(data.rows || []);
  const hasRows = (data.rows || []).length > 0;

  return (
    <div className={styles.balanceView}>
      <BalanceLegend />
      <div className={styles.balanceBadgeRow}>
        <span
          className={`${styles.balanceBadge}${
            data.balanced_check ? ` ${styles.balanceBadgeOk}` : ` ${styles.balanceBadgeBad}`
          }`}
        >
          {data.balanced_check ? "Cuadra" : "No cuadra"}
        </span>
        <span className="meta">Activos = Pasivos + Patrimonio en este período</span>
      </div>
      <dl className={styles.balanceTotalsGrid}>
        <div className={styles.balanceTotalItem}>
          <dt>Activos</dt>
          <dd>{data.assets} BOB</dd>
        </div>
        <div className={styles.balanceTotalItem}>
          <dt>Pasivos</dt>
          <dd>{data.liabilities} BOB</dd>
        </div>
        <div className={styles.balanceTotalItem}>
          <dt>Patrimonio</dt>
          <dd>{data.equity} BOB</dd>
        </div>
        <div className={styles.balanceTotalItem}>
          <dt>Retiros del dueño</dt>
          <dd>{data.equity_draws} BOB</dd>
        </div>
      </dl>
      {!hasRows ? (
        <p className="meta">Sin saldos en este período.</p>
      ) : (
        <div className={styles.balanceGrid}>
          <BalancePanel title="Activos" rows={assets} totalLabel="Total activos" />
          <BalancePanel
            title="Pasivos y patrimonio"
            rows={liabilities}
            totalLabel="Total pasivos y patrimonio"
          />
        </div>
      )}
    </div>
  );
}