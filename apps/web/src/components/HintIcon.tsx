import { Info } from "lucide-react";

/**
 * A standing explanation, kept out of the layout: shown on hover or keyboard focus.
 * The bubble is CSS text, so it never becomes part of a heading's or label's name.
 */
export function HintIcon({ text }: { text: string }) {
  return (
    <span className="hint-icon" tabIndex={0} role="img" aria-label={text} data-hint={text}>
      <Info size={14} aria-hidden="true" />
    </span>
  );
}

/** A section heading with its hint beside it rather than inside it. */
export function HintedHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="hinted-heading">
      <h3>{title}</h3>
      <HintIcon text={hint} />
    </div>
  );
}
