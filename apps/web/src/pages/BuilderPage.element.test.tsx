import { describe, expect, it } from "vitest";
import { defineAgentConversation, type AgentConversationElement, type ConversationTransport } from "@opendataagent/agent-conversation";

/**
 * The conversation area is a custom element, so it only works if something
 * registers it. Nothing else in this suite mounts it, which is how the
 * registration went missing without a single test, type check or build
 * noticing: an unregistered tag renders as an inert empty box, silently.
 */
describe("the conversation element is usable", () => {
  it("registers under the tag BuilderPage renders", () => {
    defineAgentConversation();

    expect(customElements.get("dataagent-conversation")).toBeTypeOf("function");
  });

  it("upgrades into a real element with the SDK's API, not an unknown tag", async () => {
    defineAgentConversation();

    const el = document.createElement("dataagent-conversation");
    document.body.appendChild(el);
    await customElements.whenDefined("dataagent-conversation");

    // An unregistered tag is an HTMLElement with none of these.
    expect(el.shadowRoot, "the element must attach a shadow root").toBeTruthy();
    for (const method of ["sendMessage", "cancel", "reload", "focus", "focusMessage"]) {
      expect(
        typeof (el as unknown as Record<string, unknown>)[method],
        `${method}() must exist for BuilderPage to drive the conversation`,
      ).toBe("function");
    }

    el.remove();
  });

  it("dispatches dataagent-plan-open from 查看完整计划 without opening on body click", async () => {
    defineAgentConversation();

    const el = document.createElement("dataagent-conversation") as AgentConversationElement;
    el.transportFactory = () =>
      ({
        loadConversation: async () => ({
          messages: [
            {
              id: "msg-plan",
              role: "assistant",
              content: "",
              status: "success",
              blocks: [
                {
                  type: "permission_request",
                  request_id: "plan-1",
                  tool_name: "ExitPlanMode",
                  risk_level: "plan",
                  summary: "# 星河采购建模计划\n\n## 步骤\n1. 新建对象 **供应商**",
                  decision: "allow",
                },
              ],
            },
          ],
          run: null,
        }),
        sendMessage: async () => ({ taskId: "t-1", status: "running", detail: "" }),
        cancelRun: async () => ({ taskId: "t-1", status: "cancelled", detail: "" }),
        submitInteraction: async () => {},
        fileUrl: (p) => p,
        async *streamEvents() {},
      }) satisfies ConversationTransport;
    el.endpoint = "/api/v1/workspaces/w1/sessions/s1/agent-conversation";
    document.body.appendChild(el);

    const viewBtn = await new Promise<HTMLElement>((resolve, reject) => {
      const deadline = Date.now() + 2000;
      const poll = () => {
        const found = el.shadowRoot?.querySelector(".dac-plan-view-btn") as HTMLElement | null;
        if (found) return resolve(found);
        if (Date.now() > deadline) return reject(new Error("plan card did not render"));
        setTimeout(poll, 10);
      };
      poll();
    });

    const opened: unknown[] = [];
    el.addEventListener("dataagent-plan-open", (event) => {
      event.preventDefault();
      opened.push((event as CustomEvent).detail);
    });

    (el.shadowRoot?.querySelector(".dac-plan-body") as HTMLElement | null)?.click();
    expect(opened).toEqual([]);

    viewBtn.click();
    expect(opened).toEqual([
      {
        title: "星河采购建模计划",
        body: "## 步骤\n1. 新建对象 **供应商**",
        markdown: "# 星河采购建模计划\n\n## 步骤\n1. 新建对象 **供应商**",
        requestId: "plan-1",
      },
    ]);

    el.remove();
  });
});
