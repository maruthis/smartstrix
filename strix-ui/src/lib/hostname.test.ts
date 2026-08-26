import { describe, expect, it } from "vitest";
import { hostnameFromInput } from "./hostname";

describe("hostnameFromInput", () => {
  it("returns a bare hostname unchanged, lowercased", () => {
    expect(hostnameFromInput("APP.Example.COM")).toBe("app.example.com");
  });

  it("strips scheme, path, query, and trailing slash from a pasted URL", () => {
    expect(hostnameFromInput("https://dev-stag-agui.techsophy.com/ ")).toBe("dev-stag-agui.techsophy.com");
    expect(hostnameFromInput("https://app.example.com/path?q=1")).toBe("app.example.com");
    expect(hostnameFromInput("http://app.example.com:443/")).toBe("app.example.com");
  });

  it("treats a host with a path as the host", () => {
    expect(hostnameFromInput("app.example.com/redirect")).toBe("app.example.com");
  });

  it("rejects userinfo so a URL cannot smuggle a different host", () => {
    expect(hostnameFromInput("https://evil.example.com@169.254.169.254")).toBe("");
  });

  it("returns empty for blank input", () => {
    expect(hostnameFromInput("   ")).toBe("");
  });
});
