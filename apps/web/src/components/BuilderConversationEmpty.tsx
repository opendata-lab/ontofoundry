/* Hallmark · component: conversation empty state · genre: modern-minimal
 * theme: existing Cobalt · pre-emit critique: P4 H5 E4 S5 R5 V4
 * Static guidance; conversation states are owned by the SDK empty slot.
 */
import { MessageSquareText } from "lucide-react";

export function BuilderConversationEmpty() {
  return (
    <section slot="empty" className="builder-chat-empty" aria-label="本体构建引导">
      <MessageSquareText size={24} strokeWidth={1.6} aria-hidden="true" />
      <h2>开始本体构建</h2>
      <p>从业务问题出发，梳理对象、属性和关系。</p>
      <p className="builder-chat-empty-help">
        在左侧配置材料和场景，点击「开始建模」。也可以先在下方提问，明确建模范围。
      </p>
    </section>
  );
}
