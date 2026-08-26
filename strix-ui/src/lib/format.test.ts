import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatDate, timeAgo } from "./format";

const NOW = new Date("2026-01-15T12:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("timeAgo", () => {
  it("returns 'just now' for very recent timestamps", () => {
    expect(timeAgo(new Date(NOW.getTime() - 5_000).toISOString())).toBe("just now");
  });

  it("returns minutes ago", () => {
    expect(timeAgo(new Date(NOW.getTime() - 5 * 60_000).toISOString())).toBe("5m ago");
  });

  it("returns hours ago", () => {
    expect(timeAgo(new Date(NOW.getTime() - 3 * 60 * 60_000).toISOString())).toBe("3h ago");
  });

  it("returns days ago", () => {
    expect(timeAgo(new Date(NOW.getTime() - 5 * 24 * 60 * 60_000).toISOString())).toBe("5d ago");
  });

  it("falls back to a locale date beyond 30 days", () => {
    const old = new Date(NOW.getTime() - 45 * 24 * 60 * 60_000);
    expect(timeAgo(old.toISOString())).toBe(old.toLocaleDateString());
  });

  it("handles timestamps without a trailing Z", () => {
    expect(timeAgo("2026-01-15T11:59:55")).toBe("just now");
  });
});

describe("formatDate", () => {
  it("formats an ISO timestamp as a locale string", () => {
    expect(formatDate("2026-01-15T12:00:00Z")).toBe(new Date("2026-01-15T12:00:00Z").toLocaleString());
  });

  it("handles timestamps without a trailing Z", () => {
    expect(formatDate("2026-01-15T12:00:00")).toBe(new Date("2026-01-15T12:00:00Z").toLocaleString());
  });
});
