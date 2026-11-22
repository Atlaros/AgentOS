import { describe, expect, it } from "vitest";
import {
  buildExportHref,
  EXPORT_FORMAT,
  EXPORT_TARGET,
  formatExportPeriodLabel,
  TARGET_FORMATS,
} from "./export-links";

describe("export-links", () => {
  it("lists formats per export target", () => {
    expect(TARGET_FORMATS[EXPORT_TARGET.MAYOR]).toEqual([EXPORT_FORMAT.XLSX]);
    expect(TARGET_FORMATS[EXPORT_TARGET.DIARIO]).toContain(EXPORT_FORMAT.PDF);
  });

  it("builds a period export href without a custom range", () => {
    const href = buildExportHref(EXPORT_TARGET.HECHOS, EXPORT_FORMAT.CSV, {
      period: "week",
      from: "",
      to: "",
      status: "posted",
    });
    expect(href.startsWith("/api/backend/api/ledger/export?")).toBe(true);
    expect(href).toContain("format=csv");
    expect(href).toContain("period=week");
    expect(href).toContain("status=posted");
  });

  it("prefers an explicit from/to range over the period preset", () => {
    const href = buildExportHref(EXPORT_TARGET.DIARIO, EXPORT_FORMAT.XLSX, {
      period: "month",
      from: "2026-01-01",
      to: "2026-01-31",
    });
    expect(href).toContain("from=2026-01-01");
    expect(href).toContain("to=2026-01-31");
    expect(href).not.toContain("period=");
  });

  it("labels the export period for the UI", () => {
    expect(
      formatExportPeriodLabel(
        { period: "month", from: "", to: "" },
        { from: "2026-11-01", to: "2026-11-30", preset: "month" },
      ),
    ).toBe("2026-11-01 → 2026-11-30 (Mes)");
    expect(formatExportPeriodLabel({ period: "week", from: "", to: "" })).toBe("Semana");
  });
});
