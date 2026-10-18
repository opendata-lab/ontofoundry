import { MessageSquareText } from "lucide-react";

/** Static guidance; conversation states are owned by the SDK empty slot. */
export function BuilderConversationEmpty() {
  return (
    <section
      slot="empty"
      className="mt-[clamp(32px,8vh,80px)] mb-8 max-w-[360px] min-w-0 text-left font-sans [overflow-wrap:anywhere]"
      aria-label="本体构建引导"
    >
      <MessageSquareText size={24} strokeWidth={1.6} aria-hidden="true" className="mb-5 block text-accent" />
      <h2 className="m-0 mb-3 text-[19px] leading-normal font-semibold text-ink">开始本体构建</h2>
      <p className="m-0 text-[13px] leading-[1.8] text-ink-2">从业务问题出发，梳理对象、属性和关系。</p>
      <p className="m-0 mt-5 text-xs leading-[1.9] text-muted">
        在左侧配置材料和场景，点击「开始建模」。也可以先在下方提问，明确建模范围。
      </p>
    </section>
  );
}
