import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** Hints remain visible inside scrolling tables, inspectors and drawers. */
export function HintIcon({ text }: { text: string }) {
  const label = text;
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();
  const [position, setPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const show = () => {
    const bounds = ref.current?.getBoundingClientRect();
    if (bounds)
      setPosition({
        left: Math.max(8, Math.min(bounds.left, window.innerWidth - 352)),
        top: bounds.top + bounds.height / 2,
      });
  };
  useEffect(() => {
    if (!position) return;
    const hide = () => setPosition(null);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [position]);
  return (
    <>
      <span
        ref={ref}
        className="hint-icon hint-icon--portal"
        tabIndex={0}
        role="img"
        aria-label={label}
        aria-describedby={position ? id : undefined}
        onMouseEnter={show}
        onMouseLeave={() => setPosition(null)}
        onFocus={show}
        onBlur={() => setPosition(null)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setPosition(null);
        }}
      >
        <Info size={14} aria-hidden="true" />
      </span>
      {position &&
        createPortal(
          <span
            id={id}
            className="hint-bubble"
            role="tooltip"
            style={{ left: position.left, top: position.top }}
          >
            {label}
          </span>,
          document.body,
        )}
    </>
  );
}
export function HintedHeading({
  title,
  hint,
}: {
  title: string;
  hint: string;
}) {
  return (
    <div className="hinted-heading">
      <h3>{title}</h3>
      <HintIcon text={hint} />
    </div>
  );
}
