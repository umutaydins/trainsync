/** How a plate is drawn: IWF colours by weight, height (diameter) and thickness relative to a 25. */
export interface PlateLook {
  color: string;
  /** Border for light plates, so a white 5 is visible on a white sheet. */
  stroke: string;
  name: string;
  /** 0..1 of the bar drawing's full plate height. */
  height: number;
  /** Thickness in drawing units. */
  width: number;
}

const LOOKS: Record<string, PlateLook> = {
  "25": { color: "#d32f2f", stroke: "#8e1c1c", name: "red", height: 1, width: 14 },
  "20": { color: "#1e5bd8", stroke: "#123a8c", name: "blue", height: 1, width: 12 },
  "15": { color: "#f2c200", stroke: "#9c7d00", name: "yellow", height: 1, width: 10 },
  "10": { color: "#2e8b3d", stroke: "#1b5424", name: "green", height: 1, width: 8 },
  "5": { color: "#f5f5f5", stroke: "#6b7280", name: "white", height: 0.62, width: 7 },
  "2.5": { color: "#1f1f1f", stroke: "#000000", name: "black", height: 0.5, width: 6 },
  "1.25": { color: "#b8bcc4", stroke: "#6b7280", name: "silver", height: 0.42, width: 5 },
};

const OTHER: PlateLook = { color: "#9aa4b2", stroke: "#5b6573", name: "grey", height: 0.36, width: 4 };

export function plateLook(kg: number): PlateLook {
  return LOOKS[String(kg)] ?? OTHER;
}

/** `[25, 15, 2.5]` → `25 + 15 + 2.5`. */
export function plateList(perSide: readonly number[]): string {
  return perSide.length === 0 ? "none (empty bar)" : perSide.join(" + ");
}
