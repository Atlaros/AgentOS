import { afterEach, describe, expect, it } from "vitest";
import { apiBaseUrl } from "./api-base";

const ORIGINAL = process.env.API_INTERNAL_URL;

afterEach(() => {
  if (ORIGINAL === undefined) {
    delete process.env.API_INTERNAL_URL;
  } else {
    process.env.API_INTERNAL_URL = ORIGINAL;
  }
});

describe("apiBaseUrl", () => {
  it("returns empty when unset", () => {
    delete process.env.API_INTERNAL_URL;
    expect(apiBaseUrl()).toBe("");
  });

  it("keeps an absolute URL and strips a trailing slash", () => {
    process.env.API_INTERNAL_URL = "https://api.example.com/";
    expect(apiBaseUrl()).toBe("https://api.example.com");
  });

  it("prefixes bare host:port with http", () => {
    process.env.API_INTERNAL_URL = "factory-api:8000";
    expect(apiBaseUrl()).toBe("http://factory-api:8000");
  });
});
