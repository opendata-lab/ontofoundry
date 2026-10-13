import { useEffect, useLayoutEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

export function moveFocus(event: KeyboardEvent<HTMLElement>, selector: string, horizontal = false) {
  const keys = horizontal ? ["ArrowLeft", "ArrowRight", "Home", "End"] : ["ArrowUp", "ArrowDown", "Home", "End"];
  if (!keys.includes(event.key)) return;
  const options = [...event.currentTarget.querySelectorAll<HTMLElement>(selector)];
  const index = options.indexOf(event.target as HTMLElement);
  if (index < 0 || !options.length) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 :
    (index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) + options.length) % options.length;
  options[next].focus({ preventScroll: true });
  if (horizontal) options[next].click();
}

/** Native top-layer popover; the fallback also supports DOM-only test environments. */
export function ReviewPopover({
  anchor, className, id, label, role = "dialog", onClose, children,
}: {
  anchor: HTMLElement;
  className: string;
  id?: string;
  label: string;
  role?: "dialog" | "menu";
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const native = typeof HTMLElement.prototype.showPopover === "function";
  useLayoutEffect(() => {
    const element = ref.current!;
    if (native) element.showPopover();
    const r = anchor.getBoundingClientRect(), p = element.getBoundingClientRect();
    element.style.left = `${Math.max(12, Math.min(r.right - p.width, window.innerWidth - p.width - 12))}px`;
    element.style.top = `${Math.max(12, window.innerHeight - r.bottom - 10 >= p.height ? r.bottom + 8 : r.top - p.height - 8)}px`;
    (element.querySelector<HTMLElement>("[data-initial-focus]") ??
      element.querySelector<HTMLElement>("input:checked") ??
      element.querySelector<HTMLElement>("input, button:not(:disabled)") ?? element).focus({ preventScroll: true });
    const outside = (event: MouseEvent) => {
      if (!element.contains(event.target as Node) && !anchor.contains(event.target as Node)) close.current();
    };
    const resize = () => close.current();
    const toggle = (event: Event) => {
      if ((event as Event & { newState: string }).newState === "closed" &&
        !element.matches(":popover-open")) close.current();
    };
    document.addEventListener("click", outside);
    window.addEventListener("resize", resize);
    element.addEventListener("toggle", toggle);
    return () => {
      document.removeEventListener("click", outside);
      window.removeEventListener("resize", resize);
      element.removeEventListener("toggle", toggle);
      if (native && element.matches(":popover-open")) element.hidePopover();
    };
  }, [anchor, native]);
  return <div ref={ref} id={id} className={className} popover={native ? "auto" : undefined}
    role={role} aria-label={label} tabIndex={-1} onKeyDown={(event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        anchor.focus({ preventScroll: true });
      } else moveFocus(event, role === "menu" ? "button:not(:disabled)" : "input");
    }}>{children}</div>;
}

export function ReviewDialog({ className, label, onClose, children }: {
  className: string;
  label: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const element = ref.current!;
    const closed = () => { if (!element.open) close.current(); };
    element.addEventListener("close", closed);
    if (!element.open) element.showModal();
    element.querySelector<HTMLElement>("[data-initial-focus]")?.focus({ preventScroll: true });
    return () => {
      element.removeEventListener("close", closed);
      if (element.open) element.close();
    };
  }, []);
  return <dialog ref={ref} className={className} aria-label={label}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClick={(event) => {
      if (event.target !== event.currentTarget) return;
      const r = event.currentTarget.getBoundingClientRect();
      if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) onClose();
    }}>{children}</dialog>;
}
