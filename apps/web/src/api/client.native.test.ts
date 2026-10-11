import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelingSession, NativeDraft, PublishPreview } from "./types";
import fixture from "../lib/nativeDraft.fixture.json";
import { modelingApi, publishApi } from "./client";

const response = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.unstubAllGlobals());

describe("native API boundary", () => {
  it("hydrates the existing mapping form without adding it to persisted draft JSON", async () => {
    const draft = structuredClone(fixture) as NativeDraft;
    const form = { mappings: [], joins: {} };
    const fetch = vi.fn().mockImplementationOnce(() => response(draft)).mockImplementationOnce(() => response(form));
    vi.stubGlobal("fetch", fetch);
    const snapshot = await modelingApi.snapshot(draft.workspace_id) as NativeDraft;
    expect(snapshot._legacy_form).toEqual(form);
    fetch.mockImplementationOnce(() => response({ id: "s", draft, revision: 1 }));
    await modelingApi.save({ id: "s", workspace_id: draft.workspace_id, revision: 0 } as ModelingSession, snapshot);
    const request = JSON.parse(fetch.mock.calls[2][1].body);
    expect(request.draft.schema_version).toBe("3");
    expect(request.draft).not.toHaveProperty("_legacy_form");
    expect(request.legacy_mappings).toEqual([]);
    expect(request.draft.link_types).toEqual(draft.link_types);
  });
  it("publishes using the reviewed preview revision", async () => {
    const draft = structuredClone(fixture) as NativeDraft;
    const session = { id: "s", workspace_id: draft.workspace_id, revision: 7, draft } as ModelingSession;
    const preview = { session_revision: 8, current_version_id: null, merged_snapshot_sha256: "preview-hash" } as PublishPreview;
    const fetch = vi.fn().mockImplementationOnce(() => response({ session: { ...session, revision: 9 } }));
    vi.stubGlobal("fetch", fetch);
    await publishApi.publish(session, preview, "publish");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toMatch(/publish$/);
    expect(JSON.parse(fetch.mock.calls[0][1].body).expected_session_revision).toBe(8);
  });

});
