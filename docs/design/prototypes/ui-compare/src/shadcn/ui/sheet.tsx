import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** Right-side panel (shadcn/ui Sheet) built on Radix Dialog. */
export function Sheet({ open, onOpenChange, title, footer, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; footer: ReactNode; children: ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#14203a]/45" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-40 flex w-[760px] max-w-full flex-col bg-surface shadow-2xl outline-none">
          <div className="flex items-center justify-between border-b border-rule-soft px-6 py-4">
            <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
            <Dialog.Close className="rounded-sm p-1 text-muted hover:bg-surface-soft" aria-label="关闭"><X size={18} /></Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{title}</Dialog.Description>
          <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
          <div className="flex justify-end gap-2 border-t border-rule-soft px-6 py-3">{footer}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
