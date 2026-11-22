import { describe, expect, it } from "vitest";
import { isSupplierTabId, resolveSupplierTab, supplierHref } from "./suppliers-tab";

describe("suppliers-tab", () => {
  it("accepts only known tab ids", () => {
    expect(isSupplierTabId("directorio")).toBe(true);
    expect(isSupplierTabId("reposicion")).toBe(true);
    expect(isSupplierTabId("ordenes")).toBe(true);
    expect(isSupplierTabId("caja")).toBe(false);
    expect(isSupplierTabId(null)).toBe(false);
  });

  it("falls back to directorio", () => {
    expect(resolveSupplierTab("ordenes")).toBe("ordenes");
    expect(resolveSupplierTab("nope")).toBe("directorio");
    expect(resolveSupplierTab(undefined)).toBe("directorio");
  });

  it("builds the suppliers href", () => {
    expect(supplierHref("reposicion")).toBe("/suppliers?tab=reposicion");
  });
});
