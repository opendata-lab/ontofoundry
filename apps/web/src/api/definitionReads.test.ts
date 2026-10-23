import { describe, expect, it, vi } from "vitest";
import { DefinitionReads } from "./definitionReads";
import type { Presentation } from "./types";
const value = () => ({ version: { version_id: "v1" }, model: { workspace_id: "星舟商贸", object_types: [] } }) as unknown as Presentation;
describe("immutable version definitions", () => {
  it("coalesces consumers without coupling their lifetime and retries failures", async () => {
    const cache = new DefinitionReads();
    const read = vi.fn().mockResolvedValue(value());
    const a = cache.get("w", "v1", read), b = cache.get("w", "v1", read);
    expect(a).toBe(b);
    expect(await a).toBe(await b);
    expect(read).toHaveBeenCalledTimes(1);
    const fail = vi.fn().mockRejectedValueOnce(new Error("离线")).mockResolvedValue(value());
    await expect(cache.get("w", "v2", fail)).rejects.toThrow("离线");
    await cache.get("w", "v2", fail);
    expect(fail).toHaveBeenCalledTimes(2);
  });
  it("isolates versions, accounts, permission generations and late requests", async () => {
    const cache = new DefinitionReads();
    cache.authorize("a", "w", "member");
    let finish!: (v: Presentation) => void;
    const pending = cache.get("w", "v1", () => new Promise(resolve => { finish = resolve; }));
    cache.authorize("b", "w", "member");
    finish(value());
    await expect(pending).rejects.toThrow("授权已变化");
    const read = vi.fn().mockResolvedValue(value());
    await cache.get("w", "v1", read);
    await cache.get("w", "v2", read);
    cache.authorize("b", "w", "reader");
    await cache.get("w", "v1", read);
    expect(read).toHaveBeenCalledTimes(3);
  });
  it("bounds retained bytes and leaves editor copies independent", async () => {
    const cache = new DefinitionReads(1);
    const shared = await cache.get("w", "v1", async () => value());
    expect(cache.stats().entries).toBe(0);
    const copy = structuredClone(shared);
    copy.model.workspace_id = "月港制造";
    expect(shared.model.workspace_id).toBe("星舟商贸");
  });
});
