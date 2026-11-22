import styles from "./reports.module.css";

export interface ReportDownloads {
  csv: string;
  xlsx: string;
}

export interface ReportCard {
  id: string;
  label: string;
  description: string;
  row_count: number;
  downloads: ReportDownloads;
}

const REPORT_FORMAT = {
  CSV: "csv",
  XLSX: "xlsx",
} as const;

export type ReportFormat = (typeof REPORT_FORMAT)[keyof typeof REPORT_FORMAT];

const OPERATION_ORDER = ["orders", "payments", "stock"] as const;

const OPERATION_IDS = new Set<string>(OPERATION_ORDER);

const ACCOUNTING_IDS = new Set([
  "ledger_hechos",
  "journal",
  "mayor",
  "comprobacion",
  "resultado",
  "balance",
]);

const ACCOUNTING_ORDER = [
  "ledger_hechos",
  "journal",
  "mayor",
  "comprobacion",
  "resultado",
  "balance",
] as const;

type DownloadsPanelProps = {
  cards: ReportCard[];
  format: ReportFormat;
};

function rowLabel(count: number): string {
  return count === 1 ? "1 fila" : `${count} filas`;
}

function downloadHref(path: string): string {
  if (path.startsWith("/api/backend/")) return path;
  return `/api/backend${path}`;
}

function cardHref(card: ReportCard, format: ReportFormat): string {
  const preferred =
    format === REPORT_FORMAT.XLSX ? card.downloads.xlsx : card.downloads.csv;
  const fallback =
    format === REPORT_FORMAT.XLSX ? card.downloads.csv : card.downloads.xlsx;
  return downloadHref(preferred || fallback);
}

function partitionCards(cards: ReportCard[]): {
  operation: ReportCard[];
  accounting: ReportCard[];
} {
  const byId = new Map(cards.map((card) => [card.id, card]));
  const operation = OPERATION_ORDER.map((id) => byId.get(id)).filter(
    (card): card is ReportCard => card != null,
  );
  const orderedAccounting = ACCOUNTING_ORDER.map((id) => byId.get(id)).filter(
    (card): card is ReportCard => card != null,
  );
  return { operation, accounting: orderedAccounting };
}

function OperationCard({ card, format }: { card: ReportCard; format: ReportFormat }) {
  return (
    <article className={styles.card}>
      <h3 className={styles.cardTitle}>{card.label}</h3>
      <p className={styles.cardBody}>{card.description}</p>
      <p className={styles.count}>{rowLabel(card.row_count)}</p>
      <a className={styles.download} href={cardHref(card, format)}>
        Descargar
      </a>
    </article>
  );
}

function AccountingRow({ card, format }: { card: ReportCard; format: ReportFormat }) {
  return (
    <tr>
      <td>
        <span className={styles.accountingLabel}>{card.label}</span>
        <span className={styles.accountingDesc}>{card.description}</span>
      </td>
      <td className={styles.numeric}>{rowLabel(card.row_count)}</td>
      <td>
        <a className={styles.downloadCompact} href={cardHref(card, format)}>
          Descargar
        </a>
      </td>
    </tr>
  );
}

export function DownloadsPanel({ cards, format }: DownloadsPanelProps) {
  if (cards.length === 0) return null;
  const { operation, accounting } = partitionCards(cards);

  return (
    <div className={styles.downloadGroups}>
      {operation.length > 0 ? (
        <section className={styles.downloadSection} aria-labelledby="reports-op-heading">
          <h2 id="reports-op-heading" className={styles.sectionTitle}>
            Operación
          </h2>
          <p className={styles.sectionNote}>Ventas, cobros e inventario del período elegido.</p>
          <div className={styles.cards}>
            {operation.map((card) => (
              <OperationCard key={card.id} card={card} format={format} />
            ))}
          </div>
        </section>
      ) : null}
      {accounting.length > 0 ? (
        <section className={styles.downloadSection} aria-labelledby="reports-acc-heading">
          <h2 id="reports-acc-heading" className={styles.sectionTitle}>
            Contabilidad
          </h2>
          <p className={styles.sectionNote}>
            Archivos del libro. Para leerlos en pantalla:{" "}
            <a href="/ledger">Contabilidad</a>.
          </p>
          <div className={styles.accountingListWrap}>
            <table className={styles.accountingList}>
              <thead>
                <tr>
                  <th>Reporte</th>
                  <th>Filas</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {accounting.map((card) => (
                  <AccountingRow key={card.id} card={card} format={format} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}