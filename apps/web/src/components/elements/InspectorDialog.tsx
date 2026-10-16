import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { usePageActive } from "../../hooks/usePageTab";
import { createPortal } from "react-dom";

/** Native modal stacking keeps Escape, focus trapping and focus restoration consistent. */
export function InspectorDialog({
  title,
  children,
  onClose,
  footer,
  subtitle,
  actions,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  subtitle?: string;
  actions?: ReactNode;
  wide?: boolean;
}) {
  const active = usePageActive();
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current;
    if (active) element?.showModal();
    return () => {
      element?.close();
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [active]);
  return createPortal(
    <dialog
      ref={dialog}
      aria-labelledby={id}
      className={`om-dialog${wide ? " om-dialog-wide" : ""}`}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        const rect = e.currentTarget.getBoundingClientRect();
        if (
          e.clientX < rect.left ||
          e.clientX > rect.right ||
          e.clientY < rect.top ||
          e.clientY > rect.bottom
        )
          onClose();
      }}
    >
      <div className="om-dialog-layout">
        <header className="om-detail-head">
          <div className="om-detail-title">
            <h2 id={id}>{title}</h2>
            {subtitle && <small>{subtitle}</small>}
          </div>
          {actions}
          <button
            type="button"
            className="icon-button"
            aria-label={`关闭${title}`}
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </header>
        <div className="om-detail-content">{children}</div>
        {footer && <footer className="om-detail-foot">{footer}</footer>}
      </div>
    </dialog>,
    document.body,
  );
}
