/** The structure of the legal pages; the words live in the `legal` messages (both languages). */

export type LegalDoc = "privacy" | "terms";

export interface LegalSection {
  id: string;
  /** Keys of `sections.<id>` rendered as paragraphs, in order. */
  paragraphs: readonly string[];
  /** Keys of `sections.<id>.items` rendered as a list after the first paragraph. */
  items?: readonly string[];
}

/** When the wording last changed (shown at the top; update with the messages). */
export const LEGAL_UPDATED = "2026-10-19";

export const LEGAL_SECTIONS: Record<LegalDoc, readonly LegalSection[]> = {
  privacy: [
    { id: "who", paragraphs: ["body"] },
    {
      id: "stored",
      paragraphs: ["body"],
      items: ["account", "sessions", "training", "nutrition", "strava", "telegram", "settings"],
    },
    { id: "strava", paragraphs: ["body", "control"] },
    { id: "services", paragraphs: ["body"] },
    { id: "export", paragraphs: ["body"] },
    { id: "retention", paragraphs: ["body"] },
    { id: "cookies", paragraphs: ["body"] },
    { id: "contact", paragraphs: ["body"] },
  ],
  terms: [
    { id: "service", paragraphs: ["body"] },
    { id: "account", paragraphs: ["body"] },
    { id: "coach", paragraphs: ["body"] },
    { id: "strava", paragraphs: ["body"] },
    { id: "availability", paragraphs: ["body"] },
    { id: "ending", paragraphs: ["body"] },
    { id: "changes", paragraphs: ["body"] },
    { id: "contact", paragraphs: ["body"] },
  ],
};
