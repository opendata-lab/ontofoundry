import type { DetailedHTMLProps, HTMLAttributes, Ref } from "react";

/**
 * JSX typing for the SDK's custom element.
 *
 * Only `endpoint` and `placeholder` are attributes. Everything object- or
 * function-valued is a JS property set through a ref, because an HTML
 * attribute cannot carry one.
 */
export type AgentConversationElement = HTMLElement & {
  /**
   * The conversation key. Assigning a different value aborts the live stream,
   * clears state and loads the new conversation — this is the only way to
   * switch. Do not call reload() for that.
   */
  endpoint: string;
  placeholder: string;
  active: boolean;
  disabled: boolean;
  /** Composer draft; readable and writable. */
  value: string;
  /** Consulted once, on first send, and only while endpoint is empty. */
  endpointResolver?: () => string | Promise<string>;

  /** Same conversation, fetched again. Not a switch. */
  reload(): Promise<void>;
  sendMessage(
    content?: string,
    options?: { metadata?: Record<string, unknown>; clearDraft?: boolean },
  ): Promise<void>;
  cancel(): Promise<void>;
  focus(): void;
};

export type RunStatus =
  | "idle"
  | "queued"
  | "running"
  | "waiting_input"
  | "waiting_permission"
  | "finished"
  | "cancelled"
  | "failed";

export type RunChangeDetail = {
  taskId: string;
  status: RunStatus;
  detail: string;
};

export type CompleteDetail = {
  taskId: string;
  status: RunStatus;
  /** Whatever was passed to sendMessage, handed back verbatim. */
  metadata?: { mode?: "chat" | "model" } & Record<string, unknown>;
};

export type ErrorDetail = {
  code:
    | "transport_unreachable"
    | "conversation_unavailable"
    | "stream_interrupted"
    | "protocol_error";
  message: string;
  /** How to fix it, when the backend knows. Worth showing to the user. */
  hint?: string;
};

type AgentConversationProps = DetailedHTMLProps<
  HTMLAttributes<AgentConversationElement> & {
    ref?: Ref<AgentConversationElement>;
    endpoint?: string;
    placeholder?: string;
  },
  AgentConversationElement
>;

// Both spellings: React 18 moved IntrinsicElements under the React namespace,
// but the global one is still what older tooling in this project consults.
declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "dataagent-conversation": AgentConversationProps;
    }
  }
}

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "dataagent-conversation": AgentConversationProps;
    }
  }
}
