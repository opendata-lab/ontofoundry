import { describe, expect, it } from "vitest";
import { defineAgentConversation } from "@opendataworks/agent-conversation";

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
});
