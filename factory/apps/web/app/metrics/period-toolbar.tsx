"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AlertsDrawer } from "./alerts-drawer";
import { PeriodRangeForm } from "./period-range";
import styles from "./metrics.module.css";
import type { ThresholdValues } from "./thresholds-form";

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

const STORAGE_KEY = "closet.analytics.period";

type StoredPeriod = {
  period: PeriodId;
  dateFrom: string;
  dateTo: string;
};

type PeriodToolbarProps = {
  active: string;
  explicit: boolean;
  from: string;
  to: string;
  dateFrom: string;
  dateTo: string;
  canEdit: boolean;
  thresholds: ThresholdValues | null;
};

function isPeriodId(value: string): value is PeriodId {
  return (
    value === PERIOD.TODAY ||
    value === PERIOD.WEEK ||
    value === PERIOD.MONTH ||
    value === PERIOD.RANGE
  );
}

function isStoredPeriod(value: unknown): value is StoredPeriod {
  if (typeof value !== "object" || value === null) return false;
  if (!("period" in value) || !("dateFrom" in value) || !("dateTo" in value)) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.period === "string" &&
    isPeriodId(record.period) &&
    typeof record.dateFrom === "string" &&
    typeof record.dateTo === "string"
  );
}

export function PeriodToolbar({
  active,
  explicit,
  from,
  to,
  dateFrom,
  dateTo,
  canEdit,
  thresholds,
}: PeriodToolbarProps) {
  const router = useRouter();
  const [rangeOpen, setRangeOpen] = useState(active === PERIOD.RANGE);

  useEffect(() => {
    if (explicit) {
      if (!isPeriodId(active)) return;
      try {
        const payload: StoredPeriod = { period: active, dateFrom, dateTo };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch {
        /* Storage can be blocked. The period in the URL still stands. */
      }
      return;
    }
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (!isStoredPeriod(parsed) || parsed.period === PERIOD.WEEK) return;
      if (parsed.period === PERIOD.RANGE) {
        if (!parsed.dateFrom || !parsed.dateTo) return;
        const params = new URLSearchParams({
          period: PERIOD.RANGE,
          date_from: parsed.dateFrom,
          date_to: parsed.dateTo,
        });
        router.replace(`/metrics?${params.toString()}`);
        return;
      }
      router.replace(`/metrics?period=${parsed.period}`);
    } catch {
      /* Ignore a broken or unavailable store and keep the default period. */
    }
  }, [active, dateFrom, dateTo, explicit, router]);

  return (
    <>
      <nav className={styles.toolbar} aria-label="Período">
        {PERIODS.map((item) => (
          <Link
            key={item.id}
            className={styles.period}
            href={`/metrics?period=${item.id}`}
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
        {canEdit && thresholds ? <AlertsDrawer thresholds={thresholds} /> : null}
      </nav>
      {rangeOpen ? <PeriodRangeForm from={from} to={to} /> : null}
    </>
  );
}
