const EXPORT_FORMAT = {
  CSV: "csv",
  PDF: "pdf",
  XLSX: "xlsx",
} as const;

export type ExportFormat = (typeof EXPORT_FORMAT)[keyof typeof EXPORT_FORMAT];

export const FORMAT_LABEL = {
  [EXPORT_FORMAT.CSV]: "CSV",
  [EXPORT_FORMAT.PDF]: "PDF",
  [EXPORT_FORMAT.XLSX]: "Excel",
} as const;

const EXPORT_TARGET = {
  HECHOS: "hechos",
  DIARIO: "diario",
  MAYOR: "mayor",
  COMPROBACION: "comprobacion",
  RESULTADO: "resultado",
  BALANCE: "balance",
  CONCILIACION: "conciliacion",
} as const;

export type ExportTarget = (typeof EXPORT_TARGET)[keyof typeof EXPORT_TARGET];

export const TARGET_FORMATS: Record<ExportTarget, readonly ExportFormat[]> = {
  [EXPORT_TARGET.HECHOS]: [EXPORT_FORMAT.CSV, EXPORT_FORMAT.PDF],
  [EXPORT_TARGET.DIARIO]: [EXPORT_FORMAT.CSV, EXPORT_FORMAT.PDF, EXPORT_FORMAT.XLSX],
  [EXPORT_TARGET.MAYOR]: [EXPORT_FORMAT.XLSX],
  [EXPORT_TARGET.COMPROBACION]: [EXPORT_FORMAT.CSV, EXPORT_FORMAT.XLSX],
  [EXPORT_TARGET.RESULTADO]: [EXPORT_FORMAT.XLSX, EXPORT_FORMAT.PDF],
  [EXPORT_TARGET.BALANCE]: [EXPORT_FORMAT.XLSX, EXPORT_FORMAT.PDF],
  [EXPORT_TARGET.CONCILIACION]: [EXPORT_FORMAT.XLSX],
};

const TARGET_PATH: Record<ExportTarget, string> = {
  [EXPORT_TARGET.HECHOS]: "/api/backend/api/ledger/export",
  [EXPORT_TARGET.DIARIO]: "/api/backend/api/journal/export",
  [EXPORT_TARGET.MAYOR]: "/api/backend/api/journal/ledger",
  [EXPORT_TARGET.COMPROBACION]: "/api/backend/api/journal/trial-balance",
  [EXPORT_TARGET.RESULTADO]: "/api/backend/api/journal/income",
  [EXPORT_TARGET.BALANCE]: "/api/backend/api/journal/balance-sheet",
  [EXPORT_TARGET.CONCILIACION]: "/api/backend/api/journal/bank-recon",
};

export type ExportPeriodFilters = {
  period: string;
  from: string;
  to: string;
  account?: string;
  source?: string;
  status?: string;
  category?: string;
  method?: string;
};

const PERIOD_PRESET_LABEL = {
  today: "Hoy",
  week: "Semana",
  month: "Mes",
} as const;

type PeriodPreset = keyof typeof PERIOD_PRESET_LABEL;

function isPeriodPreset(value: string): value is PeriodPreset {
  return value in PERIOD_PRESET_LABEL;
}

export function formatExportPeriodLabel(
  filters: Pick<ExportPeriodFilters, "period" | "from" | "to">,
  periodInfo?: { from: string; to: string; preset: string | null } | null,
): string {
  if (periodInfo?.from && periodInfo?.to) {
    const base = `${periodInfo.from} → ${periodInfo.to}`;
    if (periodInfo.preset) {
      const preset = isPeriodPreset(periodInfo.preset)
        ? PERIOD_PRESET_LABEL[periodInfo.preset]
        : periodInfo.preset;
      return `${base} (${preset})`;
    }
    return base;
  }
  const from = filters.from.trim();
  const to = filters.to.trim();
  if (from || to) {
    return `${from || "…"} → ${to || "…"}`;
  }
  const period = filters.period.trim() || "month";
  if (isPeriodPreset(period)) return PERIOD_PRESET_LABEL[period];
  return period;
}

export function buildExportHref(
  target: ExportTarget,
  format: ExportFormat,
  filters: ExportPeriodFilters,
): string {
  const params = new URLSearchParams();
  params.set("format", format);
  const period = filters.period.trim() || "month";
  const hasRange = Boolean(filters.from.trim() || filters.to.trim());
  if (!hasRange) {
    params.set("period", period);
  }
  for (const key of ["from", "to"] as const) {
    const trimmed = filters[key].trim();
    if (trimmed) params.set(key, trimmed);
  }
  if (target === EXPORT_TARGET.HECHOS) {
    for (const key of ["source", "status", "category", "method"] as const) {
      const trimmed = (filters[key] || "").trim();
      if (trimmed) params.set(key, trimmed);
    }
  }
  if (target === EXPORT_TARGET.MAYOR) {
    const account = (filters.account || "").trim();
    if (account) params.set("account", account);
  }
  return `${TARGET_PATH[target]}?${params.toString()}`;
}

export { EXPORT_FORMAT, EXPORT_TARGET };
