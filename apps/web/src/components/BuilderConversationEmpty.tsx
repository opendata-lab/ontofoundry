import { MessageSquareText } from "lucide-react";

/** Static guidance; conversation states are owned by the SDK empty slot. */
export function BuilderConversationEmpty() {
  return (
    <section
      slot="empty"
      className="my-6 max-w-sm min-w-0 text-left font-sans wrap-anywhere"
      aria-label="本体构建引导"
    >
      <MessageSquareText size={24} strokeWidth={1.6} aria-hidden="true" className="mb-5 block text-accent" />
      <h2 className="m-0 mb-3 text-base leading-tight font-semibold text-ink">开始本体构建</h2>
      <p className="m-0 text-sm leading-base text-ink-2">从业务问题出发，梳理对象、属性和关系。</p>
      <p className="m-0 mt-5 text-xs leading-base text-muted">
        在左侧配置材料和业务场景，在下方输入需求并发送。点击输入框内的加号，可切换本体建模或本体查询。
      </p>
    </section>
  );
}
