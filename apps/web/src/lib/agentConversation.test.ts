import { afterEach, describe, expect, it, vi } from "vitest";
import { createOntoFoundryConversationTransport } from "./agentConversation";

afterEach(() => vi.unstubAllGlobals());

describe("OntoFoundry conversation transport", () => {
  it("adds the file capability that the BFF implements", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response("report", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      }),
    );
    vi.stubGlobal("fetch", fetch);

    const transport = createOntoFoundryConversationTransport(
      "/api/conversations/c-1/",
    );
    const blob = await transport.readFile?.("output/季度 报告.txt");

    expect(await blob?.text()).toBe("report");
    expect(fetch).toHaveBeenCalledWith(
      "/api/conversations/c-1/files/output/%E5%AD%A3%E5%BA%A6%20%E6%8A%A5%E5%91%8A.txt",
      { credentials: "same-origin" },
    );
  });

  it("does not advertise optional capabilities the BFF cannot honor", () => {
    const transport = createOntoFoundryConversationTransport("/api/conversations/c-1");

    expect(transport.uploadFiles).toBeUndefined();
    expect(transport.setPermissionMode).toBeUndefined();
    expect(transport.submitFeedback).toBeUndefined();
    expect(transport.executeSql).toBeUndefined();
  });
});
