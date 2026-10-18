import type { ThemeConfig } from "antd";

/** Reads one CSS custom property from the document root; "" when it is unset. */
export type TokenReader = (name: string) => string;

const readRoot: TokenReader = (name) =>
  typeof document === "undefined"
    ? ""
    : getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/**
 * Ant Design derives hover and active shades from the seed colours and only
 * parses hex, rgb() and hsl(). Other notations are left out so Ant Design
 * keeps its own default for them.
 */
function color(value: string): string | undefined {
  return /^(#[0-9a-f]{3,8}|rgba?\(|hsla?\()/i.test(value) ? value : undefined;
}

/** "6px" → 6. Ant Design expects plain numbers for sizes. */
function pixels(value: string): number | undefined {
  const match = /^(-?\d+(?:\.\d+)?)px$/.exec(value);
  return match ? Number(match[1]) : undefined;
}

/** "1.45" → 1.45. Used for unitless line-height tokens. */
function scalar(value: string): number | undefined {
  const match = /^(-?\d+(?:\.\d+)?)$/.exec(value);
  return match ? Number(match[1]) : undefined;
}

function defined<T extends Record<string, unknown>>(input: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(input).filter(([, value]) => value !== "" && value !== undefined),
  ) as Partial<T>;
}

/**
 * Builds the Ant Design theme from the variables in styles/tokens.css, so the
 * colours, radii, typography, spacing and control metrics live in one place.
 * Must run after the stylesheet has loaded. Tokens that are missing (as in
 * jsdom tests) are left out and Ant Design falls back to its defaults.
 */
export function antdTheme(read: TokenReader = readRoot): ThemeConfig {
  const accent = color(read("--color-accent"));
  const accentHover = color(read("--color-accent-hover"));
  const accentSoft = color(read("--color-accent-soft"));
  const ink = color(read("--color-ink"));
  const ink2 = color(read("--color-ink-2"));
  const muted = color(read("--color-muted"));
  const subtle = color(read("--color-subtle"));
  const rule = color(read("--color-rule"));
  const ruleSoft = color(read("--color-rule-soft"));
  const ruleStrong = color(read("--color-rule-strong"));
  const canvas = color(read("--color-canvas"));
  const surface = color(read("--color-surface"));
  const surfaceRaised = color(read("--color-surface-raised"));
  const surfaceSoft = color(read("--color-surface-soft"));
  const success = color(read("--color-success"));
  const successSoft = color(read("--color-success-soft"));
  const warning = color(read("--color-warning"));
  const warningSoft = color(read("--color-warning-soft"));
  const danger = color(read("--color-danger"));
  const dangerSoft = color(read("--color-danger-soft"));

  const radiusXs = pixels(read("--radius-xs"));
  const radiusSm = pixels(read("--radius-sm"));
  const radiusMd = pixels(read("--radius-md"));

  const textXs = pixels(read("--text-xs"));
  const textSm = pixels(read("--text-sm"));
  const textBase = pixels(read("--text-base"));
  const leadingTight = scalar(read("--leading-tight"));
  const leadingBase = scalar(read("--leading-base"));

  const spaceXs = pixels(read("--space-xs"));
  const spaceSm = pixels(read("--space-sm"));
  const spaceMd = pixels(read("--space-md"));
  const spaceLg = pixels(read("--space-lg"));

  const controlSm = pixels(read("--control-height-sm"));
  const controlMd = pixels(read("--control-height"));
  const controlLg = pixels(read("--control-height-lg"));
  const cellPy = pixels(read("--table-cell-py"));
  const cellPx = pixels(read("--table-cell-px"));
  const cellPySm = pixels(read("--table-cell-py-sm"));
  const cellPxSm = pixels(read("--table-cell-px-sm"));

  const token = defined({
    colorPrimary: accent,
    colorPrimaryHover: accentHover,
    colorPrimaryBg: accentSoft,
    colorInfo: accent,
    colorInfoBg: accentSoft,
    colorLink: accent,
    colorLinkHover: accentHover,
    colorText: ink2,
    colorTextHeading: ink,
    colorTextSecondary: muted,
    colorTextDescription: muted,
    colorTextPlaceholder: subtle,
    colorBorder: rule,
    colorBorderSecondary: ruleSoft,
    colorSplit: rule,
    colorBgLayout: canvas,
    colorBgContainer: surface,
    colorBgElevated: surface,
    colorFillAlter: surfaceRaised,
    colorFillSecondary: surfaceSoft,
    colorFillTertiary: surfaceSoft,
    colorSuccess: success,
    colorSuccessBg: successSoft,
    colorWarning: warning,
    colorWarningBg: warningSoft,
    colorError: danger,
    colorErrorBg: dangerSoft,
    fontFamily: read("--font-body"),
    fontFamilyCode: read("--font-mono"),
    fontSizeSM: textXs,
    fontSize: textSm,
    fontSizeLG: textBase,
    fontSizeXL: textBase,
    fontSizeHeading1: textBase,
    fontSizeHeading2: textBase,
    fontSizeHeading3: textBase,
    fontSizeHeading4: textSm,
    fontSizeHeading5: textSm,
    lineHeight: leadingBase,
    lineHeightSM: leadingTight,
    lineHeightLG: leadingTight,
    borderRadiusXS: radiusXs,
    borderRadiusSM: radiusXs,
    borderRadius: radiusSm,
    borderRadiusLG: radiusMd,
    controlHeightSM: controlSm,
    controlHeight: controlMd,
    controlHeightLG: controlLg,
  });

  return {
    token,
    components: {
      Button: defined({
        borderRadius: radiusSm,
        borderRadiusSM: radiusXs,
        borderRadiusLG: radiusSm,
        controlHeight: controlMd,
        controlHeightSM: controlSm,
        controlHeightLG: controlLg,
        contentFontSize: textSm,
        contentFontSizeSM: textXs,
        contentFontSizeLG: textSm,
        paddingInline: spaceSm,
        paddingInlineSM: spaceXs,
        defaultBorderColor: rule,
        defaultColor: ink2,
        defaultBg: surface,
        defaultHoverBg: surfaceSoft,
        defaultHoverBorderColor: ruleStrong,
        defaultHoverColor: ink,
        fontWeight: 500,
        defaultShadow: "none",
        primaryShadow: "none",
      }),
      Input: defined({
        borderRadius: radiusSm,
        borderRadiusSM: radiusXs,
        borderRadiusLG: radiusSm,
        controlHeight: controlMd,
        controlHeightSM: controlSm,
        controlHeightLG: controlLg,
        inputFontSize: textSm,
        inputFontSizeSM: textXs,
        inputFontSizeLG: textSm,
        paddingInline: spaceSm,
        paddingInlineSM: spaceXs,
        activeShadow: "none",
      }),
      Select: defined({
        borderRadius: radiusSm,
        borderRadiusSM: radiusXs,
        borderRadiusLG: radiusSm,
        controlHeight: controlMd,
        controlHeightSM: controlSm,
        controlHeightLG: controlLg,
        fontSize: textSm,
        optionFontSize: textSm,
      }),
      Tabs: defined({
        titleFontSize: textSm,
        titleFontSizeSM: textXs,
        titleFontSizeLG: textSm,
        horizontalItemGutter: spaceLg,
        horizontalItemPadding: cellPy !== undefined ? `${cellPy}px 0` : undefined,
        horizontalMargin: "0",
        inkBarColor: accent,
        itemColor: muted,
        itemSelectedColor: accent,
        itemHoverColor: ink,
        colorBorderSecondary: "transparent",
      }),
      Segmented: defined({
        borderRadius: radiusSm,
        borderRadiusSM: radiusXs,
        controlHeight: controlSm,
        fontSize: textXs,
        trackBg: surfaceSoft,
        itemColor: muted,
        itemHoverColor: ink,
        itemSelectedBg: surface,
        itemSelectedColor: accent,
        controlPaddingHorizontal: spaceSm,
        controlPaddingHorizontalSM: spaceXs,
      }),
      Table: defined({
        headerBg: surfaceRaised,
        headerColor: muted,
        headerSplitColor: "transparent",
        headerBorderRadius: 0,
        borderColor: rule,
        rowHoverBg: surfaceRaised,
        fontWeightStrong: 500,
        cellFontSize: textSm,
        cellFontSizeMD: textSm,
        cellFontSizeSM: textXs,
        cellPaddingBlock: cellPy,
        cellPaddingInline: cellPx,
        cellPaddingBlockMD: cellPy,
        cellPaddingInlineMD: cellPx,
        cellPaddingBlockSM: cellPySm,
        cellPaddingInlineSM: cellPxSm,
      }),
      Tag: defined({
        borderRadiusSM: radiusXs,
        fontSizeSM: textXs,
        defaultBg: surfaceSoft,
        defaultColor: muted,
      }),
      Card: defined({
        borderRadiusLG: radiusMd,
        headerFontSize: textSm,
        headerFontSizeSM: textXs,
        paddingLG: spaceMd,
        padding: spaceMd,
      }),
      Result: defined({
        titleFontSize: textBase,
        subtitleFontSize: textSm,
        extraMargin: spaceMd !== undefined ? `${spaceMd}px 0 0` : undefined,
      }),
      Progress: defined({
        defaultColor: success,
        remainingColor: rule,
        lineBorderRadius: radiusXs,
        fontSize: textXs,
      }),
    },
  };
}
