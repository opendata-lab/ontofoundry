import { Modal, Typography } from "antd";
import type { ReactNode } from "react";
import { usePageActive } from "../../hooks/usePageTab";

/** A secondary dialog above a page or the element inspector. */
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
  return (
    <Modal
      open={active}
      onCancel={onClose}
      width={wide ? 960 : 560}
      footer={footer ?? null}
      destroyOnHidden
      closable={{ "aria-label": `关闭${title}` }}
      title={
        <div className="flex items-start gap-3 pr-8">
          <div className="min-w-0 flex-1">
            <div>{title}</div>
            {subtitle && (
              <Typography.Text type="secondary" className="text-xs font-normal">
                {subtitle}
              </Typography.Text>
            )}
          </div>
          {actions}
        </div>
      }
    >
      {children}
    </Modal>
  );
}
