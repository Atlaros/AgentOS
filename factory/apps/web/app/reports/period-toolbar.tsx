"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import styles from "./reports.module.css";

const PERIOD = {
  TODAY: "today",
  WEEK: "7d",
  MONTH: "month",
  RANGE: "range",
} as const;

type PeriodId = (typeof PERIOD)[keyof typeof PERIOD];

const PERIODS = [
  { id: PERIOD.TODAY, label: "Hoy" },
  { id: PERIOD.WEEK, label: "7 días" },
  { id: PERIOD.MONTH, label: "Mes" },
] as const;

const REPORT_FORMAT = {
  CSV: "csv",
  XLSX: "xlsx",
} as const;

type ReportFormat = (typeof REPORT_FORMAT)[keyof typeof REPORT_FORMAT];

type PeriodToolbarProps = {
  active: PeriodId;
  dateFrom: string;
  dateTo: string;
  format: ReportFormat;
  excelAvailable: boolean;
};

function downloadsHref(
  period: PeriodId,
  format: ReportFormat,
  dateFrom = "",
  dateTo = "",
): string {
  const params = new URLSearchParams({ tab: "descargas", period, format });
  if (period === PERIOD.RANGE && dateFrom && dateTo) {
    params.set("date_from", dateFrom);
    params.set("date_to", dateTo);
  }
  return `/reports?${params.toString()}`;
}

function datePart(iso: string): string {
  return iso.slice(0, 10);
}

function shiftDate(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const stamp = new Date(Date.UTC(year, month - 1, day));
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
}

function inclusiveEnd(exclusiveIso: string): string {
  const day = datePart(exclusiveIso);
  if (!day) return "";
  return shiftDate(day, -1);
}

export function PeriodToolbar({
  active,
  dateFrom,
  dateTo,
  format,
  excelAvailable,
}: PeriodToolbarProps) {
  const [rangeOpen, setRangeOpen] = useState(active === PERIOD.RANGE);
  const csvSelected = format === REPORT_FORMAT.CSV;
  const excelSelected = format === REPORT_FORMAT.XLSX;

  return (
    <>
      <div className={styles.toolbarRow}>
        <nav className={styles.toolbar} aria-label="Período">
          {PERIODS.map((item) => (
            <Link
              key={item.id}
              className={styles.period}
              href={downloadsHref(item.id, format)}
              aria-current={active === item.id ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
          <button
            type="button"
            className={styles.period}
            aria-current={active === PERIOD.RANGE ? "page" : undefined}
            aria-expanded={rangeOpen}
            onClick={() => setRangeOpen(true)}
          >
            Rango
          </button>
        </nav>
        <div className={styles.formatGroup} role="group" aria-label="Formato">
          <Link
            className={csvSelected ? styles.formatSelected : styles.format}
            href={downloadsHref(active, REPORT_FORMAT.CSV, dateFrom, dateTo)}
            aria-current={csvSelected ? "page" : undefined}
          >
            CSV
          </Link>
          {excelAvailable ? (
            <Link
              className={excelSelected ? styles.formatSelected : styles.format}
              href={downloadsHref(active, REPORT_FORMAT.XLSX, dateFrom, dateTo)}
              aria-current={excelSelected ? "page" : undefined}
            >
              Excel
            </Link>
          ) : (
            <button
              type="button"
              className={styles.format}
              disabled
              title="Excel todavía no está disponible."
            >
              Excel
            </button>
          )}
        </div>
      </div>
      {rangeOpen ? (
        <RangeForm
          from={dateFrom ? datePart(dateFrom) : ""}
          to={dateTo ? inclusiveEnd(dateTo) : ""}
          format={format}
        />
      ) : null}
    </>
  );
}

function RangeForm({ from, to, format }: { from: string; to: string; format: ReportFormat }) {
  const router = useRouter();
  const [error, setError] = useState("");

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const dateFrom = String(data.get("date_from") || "");
    const dateTo = String(data.get("date_to") || "");
    if (!dateFrom || !dateTo || dateTo < dateFrom) {
      setError("El día final no puede ser anterior al inicial.");
      return;
    }
    setError("");
    const params = new URLSearchParams({
      tab: "descargas",
      period: PERIOD.RANGE,
      format,
      date_from: `${dateFrom}T00:00:00+00:00`,
      date_to: `${shiftDate(dateTo, 1)}T00:00:00+00:00`,
    });
    router.push(`/reports?${params.toString()}`);
  }

  return (
    <form className={styles.range} onSubmit={onSubmit}>
      <label>
        Desde
        <input name="date_from" type="date" defaultValue={from} required />
      </label>
      <label>
        Hasta
        <input name="date_to" type="date" defaultValue={to} required />
      </label>
      <button type="submit">Ver rango</button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
