import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useWakeLock } from "@/lib/wake-lock";

function Probe({ active }: { active: boolean }) {
  return <p data-testid="status">{useWakeLock(active)}</p>;
}

function setWakeLock(value: unknown) {
  Object.defineProperty(navigator, "wakeLock", { value, configurable: true });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, "wakeLock");
});

describe("useWakeLock", () => {
  it("does nothing when the API is missing", () => {
    render(<Probe active />);
    expect(screen.getByTestId("status")).toHaveTextContent("idle");
  });

  it("holds the lock while active and releases it on unmount", async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    const sentinel = { released: false, release, addEventListener: vi.fn() };
    const request = vi.fn().mockResolvedValue(sentinel);
    setWakeLock({ request });
    const view = render(<Probe active />);
    await act(async () => undefined);
    expect(request).toHaveBeenCalledWith("screen");
    expect(screen.getByTestId("status")).toHaveTextContent("active");
    view.unmount();
    expect(release).toHaveBeenCalled();
  });

  it("treats a refusal as information, not an error", async () => {
    setWakeLock({ request: vi.fn().mockRejectedValue(new DOMException("battery saver", "NotAllowedError")) });
    render(<Probe active />);
    await act(async () => undefined);
    expect(screen.getByTestId("status")).toHaveTextContent("denied");
  });

  it("is not requested when inactive", () => {
    const request = vi.fn();
    setWakeLock({ request });
    render(<Probe active={false} />);
    expect(request).not.toHaveBeenCalled();
  });
});
