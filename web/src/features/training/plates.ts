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
  "25": { color: "var(--plate-red)", stroke: "var(--plate-red-edge)", name: "red", height: 1, width: 14 },
  "20": { color: "var(--plate-blue)", stroke: "var(--plate-blue-edge)", name: "blue", height: 1, width: 12 },
  "15": { color: "var(--plate-yellow)", stroke: "var(--plate-yellow-edge)", name: "yellow", height: 1, width: 10 },
  "10": { color: "var(--plate-green)", stroke: "var(--plate-green-edge)", name: "green", height: 1, width: 8 },
  "5": { color: "var(--plate-white)", stroke: "var(--plate-white-edge)", name: "white", height: 0.62, width: 7 },
  "2.5": { color: "var(--plate-black)", stroke: "var(--plate-black-edge)", name: "black", height: 0.5, width: 6 },
  "1.25": { color: "var(--plate-silver)", stroke: "var(--plate-silver-edge)", name: "silver", height: 0.42, width: 5 },
};

const OTHER: PlateLook = { color: "var(--plate-other)", stroke: "var(--plate-other-edge)", name: "grey", height: 0.36, width: 4 };

export function plateLook(kg: number): PlateLook {
  return LOOKS[String(kg)] ?? OTHER;
}

/** `[25, 15, 2.5]` → `25 + 15 + 2.5`. */
export function plateList(perSide: readonly number[]): string {
  return perSide.length === 0 ? "none (empty bar)" : perSide.join(" + ");
}
