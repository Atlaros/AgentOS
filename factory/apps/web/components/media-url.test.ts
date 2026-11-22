import { describe, expect, it } from "vitest";
import { isHttpUrl, proxyMediaUrl } from "./media-url";

describe("media-url", () => {
  it("proxies relative API media through the Next rewrite", () => {
    expect(proxyMediaUrl("/media/a.jpg")).toBe("/api/backend/media/a.jpg");
    expect(proxyMediaUrl("/api/backend/media/a.jpg")).toBe("/api/backend/media/a.jpg");
  });

  it("leaves absolute URLs alone and drops junk", () => {
    expect(proxyMediaUrl("https://cdn.example/x.png")).toBe("https://cdn.example/x.png");
    expect(proxyMediaUrl("")).toBeUndefined();
    expect(proxyMediaUrl("not-a-path")).toBeUndefined();
  });

  it("detects http(s) URLs", () => {
    expect(isHttpUrl("http://x")).toBe(true);
    expect(isHttpUrl("https://x")).toBe(true);
    expect(isHttpUrl("/media/x")).toBe(false);
  });
});
