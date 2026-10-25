import { MessageSquareText } from "lucide-react";
import type { SessionMode } from "../api/types";

/** Static guidance; conversation states are owned by the SDK empty slot. */
export function BuilderConversationEmpty({ mode }: { mode: SessionMode }) {
  return (
    <section
      slot="empty"
      className="my-6 max-w-sm min-w-0 text-left font-sans wrap-anywhere"
      aria-label="本体构建引导"
    >
      <MessageSquareText size={24} strokeWidth={1.6} aria-hidden="true" className="mb-5 block text-accent" />
      <h2 className="m-0 mb-3 text-base leading-tight font-semibold text-ink">{mode === "model" ? "开始本体构建" : "询问本体"}</h2>
      <p className="m-0 text-sm leading-base text-ink-2">
        {mode === "model" ? "从业务问题出发，梳理对象、属性和关系。" : "基于已发布的本体模型提问，例如某个对象有哪些属性、两类对象如何关联。"}
      </p>
      <p className="m-0 mt-5 text-xs leading-base text-muted">
        {mode === "model"
          ? "在左侧配置材料和业务场景，在下方输入需求并发送。"
          : "日常模式只回答问题，不生成提案。"}
        发出第一条消息后，会话模式不能再修改。
      </p>
    </section>
  );
}
