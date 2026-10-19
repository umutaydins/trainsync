import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";
import { ChangeBadge } from "@/components/ui/change";
import { CountUp } from "@/components/ui/count-up";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Segmented } from "@/components/ui/segmented";
import { Stat } from "@/components/ui/stat";
import { Empty, Failure } from "@/components/ui/states";
import { Switch } from "@/components/ui/switch";
import { ToastProvider, useToast } from "@/components/ui/toast";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";

vi.mock("motion/react", async (original) => ({
  ...(await original<typeof import("motion/react")>()),
  useReducedMotion: () => true,
}));

const PERIODS = [
  { value: "week", label: "W" },
  { value: "month", label: "M" },
  { value: "year", label: "Y" },
] as const;

function Period() {
  const [value, setValue] = useState<(typeof PERIODS)[number]["value"]>("week");
  return (
    <>
      <Segmented label="Period" value={value} options={PERIODS} onChange={setValue} />
      <output>{value}</output>
    </>
  );
}

describe("primitives (P8.12)", () => {
  it("a button renders a link when asked to", () => {
    renderWithIntl(
      <Button asChild variant="secondary">
        <a href="/x">Go</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Go" })).toHaveAttribute("href", "/x");
  });

  it("a field wires its label, hint and error", () => {
    renderWithIntl(
      <>
        <Field label="Email" hint="Your sign-in">
          <Input type="email" />
        </Field>
        <Field label="Code" error="Wrong code">
          <Input />
        </Field>
      </>,
    );
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Your sign-in");
    const code = screen.getByLabelText("Code");
    expect(code).toHaveAttribute("aria-invalid", "true");
    expect(code).toHaveAccessibleDescription("Wrong code");
  });

  it("a switch toggles with the keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithIntl(<Switch aria-label="Digests" onCheckedChange={onChange} />);
    const toggle = screen.getByRole("switch", { name: "Digests" });
    toggle.focus();
    await user.keyboard(" ");
    expect(onChange).toHaveBeenCalledWith(true);
    expect(toggle).toHaveAttribute("aria-checked", "true");
  });

  it("the segmented control keeps one option on and follows the arrow keys", async () => {
    const user = userEvent.setup();
    renderWithIntl(<Period />);
    expect(screen.getByLabelText("Period")).toBeInTheDocument();
    screen.getByRole("radio", { name: "W" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "M" })).toHaveFocus();
    await user.click(screen.getByRole("radio", { name: "Y" }));
    expect(screen.getByRole("status")).toHaveTextContent("year");
    await user.click(screen.getByRole("radio", { name: "Y" })); // clicking the active one keeps it
    expect(screen.getByRole("status")).toHaveTextContent("year");
  });

  it("a change badge reads as words and colours good and bad news", () => {
    const { rerender } = renderWithIntl(
      <ChangeBadge pct={12.4} text="12%" label="up 12% vs previous period" />,
    );
    expect(screen.getByLabelText("up 12% vs previous period")).toHaveClass("text-ok");
    rerender(<ChangeBadge pct={12.4} text="12%" label="slower" better="down" />);
    expect(screen.getByLabelText("slower")).toHaveClass("text-bad");
    rerender(<ChangeBadge pct={null} text="" label="none" />);
    expect(screen.queryByLabelText("none")).not.toBeInTheDocument();
  });

  it("a stat shows its number in the user's locale", () => {
    renderWithIntl(
      <dl>
        <Stat label="Tonnage" value={<CountUp value={41250} locale="tr" />} unit="kg" />
      </dl>,
    );
    expect(screen.getByText("41.250")).toBeInTheDocument();
  });

  it("the progress ring is a progressbar", () => {
    renderWithIntl(<ProgressRing value={0.25} label="Rest" />);
    expect(screen.getByRole("progressbar", { name: "Rest" })).toHaveAttribute("aria-valuenow", "25");
  });

  it("a dialog opens, traps focus and closes on Escape", async () => {
    const user = userEvent.setup();
    renderWithIntl(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent title="Plates" closeLabel="Close">
          <p>Body</p>
        </DialogContent>
      </Dialog>,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("dialog", { name: "Plates" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("a toast is announced", async () => {
    function Trigger() {
      const toast = useToast();
      return <button onClick={() => toast("Saved", "ok")}>Save</button>;
    }
    renderWithIntl(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    await act(async () => screen.getByRole("button", { name: "Save" }).click());
    expect((await screen.findAllByText("Saved")).length).toBeGreaterThan(0);
  });

  it("states and controls have no axe violations", async () => {
    expect(
      await violations(
        <>
          <Empty title="No workouts yet">Start one from the program.</Empty>
          <Failure title="Could not load" message="Try again" />
          <Field label="Language">
            <Select>
              <option>English</option>
            </Select>
          </Field>
          <Switch aria-label="Digests" />
          <Period />
        </>,
      ),
    ).toEqual([]);
  });
});
