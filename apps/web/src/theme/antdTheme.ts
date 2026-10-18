import type { ThemeConfig } from "antd";

/** Reads one CSS custom property from the document root; "" when it is unset. */
export type TokenReader = (name: string) => string;

const readRoot: TokenReader = (name) =>
  typeof document === "undefined"
    ? ""
    : getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/**
 * Ant Design derives hover and active shades from the seed colours and only
 * parses hex, rgb() and hsl(). Other notations (the success and danger tokens
 * use oklch) are left out so Ant Design keeps its own default for them.
 */
function color(value: string): string {
  return /^(#[0-9a-f]{3,8}|rgba?\(|hsla?\()/i.test(value) ? value : "";
}

/** "6px" → 6. Ant Design expects plain numbers for sizes. */
function pixels(value: string): number | undefined {
  const match = /^(-?\d+(?:\.\d+)?)px$/.exec(value);
  return match ? Number(match[1]) : undefined;
}

/**
 * Builds the Ant Design theme from the variables in styles/tokens.css, so the
 * colours, radius and font live in one place. Must run after the stylesheet
 * has loaded. Tokens that are missing (as in jsdom tests) are left out and
 * Ant Design falls back to its defaults.
 */
export function antdTheme(read: TokenReader = readRoot): ThemeConfig {
  const pick = {
    colorPrimary: color(read("--color-accent")),
    colorText: color(read("--color-ink-2")),
    colorTextHeading: color(read("--color-ink")),
    colorTextSecondary: color(read("--color-muted")),
    colorBorder: color(read("--color-rule")),
    colorBorderSecondary: color(read("--color-rule-soft")),
    colorBgLayout: color(read("--color-canvas")),
    colorBgContainer: color(read("--color-surface")),
    colorSuccess: color(read("--color-success")),
    colorError: color(read("--color-danger")),
    fontFamily: read("--font-body"),
    borderRadius: pixels(read("--radius-sm")),
    borderRadiusSM: pixels(read("--radius-xs")),
    borderRadiusLG: pixels(read("--radius-md")),
  };
  const token = Object.fromEntries(
    Object.entries(pick).filter(([, value]) => value !== "" && value !== undefined),
  );
  // The workbench is compact: 13px controls and pill-shaped buttons, as the
  // pages looked before the move to Ant Design.
  return {
    token: { ...token, fontSize: 13 },
    components: {
      Button: { borderRadius: 16, borderRadiusLG: 20, borderRadiusSM: 12, fontWeight: 500 },
    },
  };
}
