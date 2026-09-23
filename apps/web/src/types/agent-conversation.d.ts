import type { AgentConversationEventMap } from "@opendataworks/agent-conversation";

// Keep one source of truth for the element, transport, message and React JSX
// contracts. The package checks its JSX augmentation against React 18 and 19;
// duplicating that augmentation here is how a consumer silently drifts when
// the SDK adds a property or changes a method signature.
export type * from "@opendataworks/agent-conversation";

export type RunChangeDetail =
  AgentConversationEventMap["dataagent-run-change"]["detail"];
export type CompleteDetail =
  AgentConversationEventMap["dataagent-complete"]["detail"];
export type ErrorDetail = AgentConversationEventMap["dataagent-error"]["detail"];
