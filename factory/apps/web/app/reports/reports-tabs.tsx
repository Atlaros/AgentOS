import Link from "next/link";

import styles from "./reports.module.css";

const REPORT_TAB = {
  DOWNLOADS: "descargas",
  FOLLOWUP: "seguimiento",
} as const;

export type ReportTabId = (typeof REPORT_TAB)[keyof typeof REPORT_TAB];

const REPORT_TAB_IDS = [REPORT_TAB.DOWNLOADS, REPORT_TAB.FOLLOWUP] as const;

const TAB_LABELS: Record<ReportTabId, string> = {
  descargas: "Descargas",
  seguimiento: "Seguimiento",
};

const TAB_HINTS: Record<ReportTabId, string> = {
  descargas: "bajar archivos",
  seguimiento: "cobrar / recontactar",
};

export function resolveReportTab(raw: string): ReportTabId {
  if (raw === REPORT_TAB.DOWNLOADS) return REPORT_TAB.DOWNLOADS;
  return REPORT_TAB.FOLLOWUP;
}

function tabHref(tab: ReportTabId): string {
  return `/reports?tab=${tab}`;
}

export function ReportsTabs({ activeTab }: { activeTab: ReportTabId }) {
  return (
    <nav className={styles.tabNav} aria-label="Secciones de reportes">
      <div className={styles.tabList} role="tablist">
        {REPORT_TAB_IDS.map((tab) => {
          const selected = tab === activeTab;
          const hint = TAB_HINTS[tab];
          return (
            <Link
              key={tab}
              href={tabHref(tab)}
              role="tab"
              aria-selected={selected}
              title={`${TAB_LABELS[tab]} · ${hint}`}
              className={selected ? styles.tabSelected : styles.tab}
              scroll={false}
            >
              {TAB_LABELS[tab]}
            </Link>
          );
        })}
      </div>
      <p className={styles.tabHintRow} aria-hidden="true">
        <span className={activeTab === REPORT_TAB.DOWNLOADS ? styles.tabHintActive : styles.tabHint}>
          Descargas · {TAB_HINTS.descargas}
        </span>
        <span className={styles.tabHintSep}>·</span>
        <span
          className={activeTab === REPORT_TAB.FOLLOWUP ? styles.tabHintActive : styles.tabHint}
        >
          Seguimiento · {TAB_HINTS.seguimiento}
        </span>
      </p>
    </nav>
  );
}