"use client";

import { useEffect, useState } from "react";

import {
  buildExportHref,
  FORMAT_LABEL,
  formatExportPeriodLabel,
  TARGET_FORMATS,
  type ExportPeriodFilters,
  type ExportTarget,
} from "./export-links";
import styles from "./ledger.module.css";

function useCanExport(): boolean {
  const [canExport, setCanExport] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backend/api/metrics?period=7d", { cache: "no-store" })
      .then((res) => {
        if (!cancelled) setCanExport(res.status !== 403);
      })
      .catch(() => {
        /* keep default visible; server still enforces 403 */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return canExport;
}

export function ExportMenu({
  target,
  filters,
  periodLabel,
}: {
  target: ExportTarget;
  filters: ExportPeriodFilters;
  periodLabel?: string;
}) {
  const canExport = useCanExport();
  if (!canExport) return null;

  const formats = TARGET_FORMATS[target];
  const label = periodLabel || formatExportPeriodLabel(filters);

  return (
    <div className={styles.exportToolbar} role="region" aria-label="Descargar libro contable">
      <div className={styles.exportToolbarHead}>
        <span className={styles.exportToolbarLabel}>Descargar</span>
        <span className={styles.exportPeriodInline}>Período: {label}</span>
      </div>
      <div className={styles.exportRow} role="group" aria-label="Formatos de descarga">
        {formats.map((format) => (
          <a
            key={format}
            className={styles.exportLink}
            href={buildExportHref(target, format, filters)}
            target="_blank"
            rel="noreferrer"
          >
            {FORMAT_LABEL[format]}
          </a>
        ))}
      </div>
    </div>
  );
}