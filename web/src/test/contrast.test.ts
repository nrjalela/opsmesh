// WCAG AA contrast for every text/background pair the site uses, read from the CSS tokens.
// Text needs 4.5:1; UI edges and chart marks (non-text) need 3:1.
import { describe, expect, it } from "vitest";
import css from "../styles.css?raw";

const root = css.slice(css.indexOf(":root {"), css.indexOf("}", css.indexOf(":root {")));
const tokens = Object.fromEntries(
  [...root.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)].map((m) => [m[1], m[2].toLowerCase()]),
);

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, where it's used]
const TEXT: [string, string, string][] = [
  ["ink", "bg", "body text"],
  ["ink", "surface", "text in cards and tables"],
  ["ink", "accent-wash", "text in highlighted (hover/selected) rows"],
  ["ink", "surface-2", "text on quiet fills"],
  ["ink-2", "bg", "secondary text"],
  ["ink-2", "surface", "secondary text in cards"],
  ["ink-2", "surface-2", "segmented control labels"],
  ["ink-2", "neutral-wash", "neutral banner, person tag"],
  ["muted", "bg", "captions, kicker labels, footer"],
  ["muted", "surface", "table headers, card captions"],
  ["muted", "accent-wash", "muted text in highlighted rows"],
  ["muted", "surface-2", "muted text on quiet fills"],
  ["accent", "bg", "links, active nav, quiet buttons"],
  ["accent", "surface", "links inside cards"],
  ["accent", "accent-wash", "links in highlighted rows"],
  ["accent-strong", "accent-wash", "count badge, selected filter, AI-agent tag, posted banner"],
  ["on-accent", "accent", "primary button"],
  ["on-accent", "accent-strong", "primary button, hover"],
  ["good", "good-wash", "posted pill"],
  ["wait", "wait-wash", "waiting pill, invoice remarks callout"],
  ["wait", "bg", "low-confidence value"],
  ["wait", "surface", "low-confidence value in cards"],
  ["danger", "bg", "errors, failed checks"],
  ["danger", "surface", "failed checks in cards"],
  ["neutral", "neutral-wash", "rejected pill"],
  ["bg", "ink", "toast and chart tooltip"],
];

const NON_TEXT: [string, string, string][] = [
  ["accent", "surface", "chart bars on a card"],
  ["accent", "bg", "focus ring, active nav underline"],
  ["input-border", "bg", "note field edge"],
];

describe("theme contrast (WCAG AA)", () => {
  it("defines every token it checks", () => {
    for (const [fg, bg] of [...TEXT, ...NON_TEXT]) {
      expect(tokens[fg], fg).toMatch(/^#/);
      expect(tokens[bg], bg).toMatch(/^#/);
    }
  });

  it.each(TEXT)("text: %s on %s (%s) is at least 4.5:1", (fg, bg) => {
    expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it.each(NON_TEXT)("non-text: %s on %s (%s) is at least 3:1", (fg, bg) => {
    expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(3);
  });

  it("uses the requested palette", () => {
    expect(tokens.bg).toBe("#ffffff");
    expect(tokens.surface).toBe("#f6faf6");
    expect(tokens.accent).toBe("#2f6b3f");
    expect(tokens["accent-wash"]).toBe("#e6f2e8");
  });
});
