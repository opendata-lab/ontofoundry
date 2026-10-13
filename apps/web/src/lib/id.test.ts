import { afterEach, describe, expect, it, vi } from "vitest";
import { newId } from "./id";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newId", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("works over plain http, where crypto.randomUUID is missing", () => {
    const real = globalThis.crypto;
    vi.stubGlobal("crypto", { getRandomValues: real.getRandomValues.bind(real) });
    const ids = new Set(Array.from({ length: 200 }, newId));
    expect(ids.size).toBe(200);
    for (const id of ids) expect(id).toMatch(UUID_V4);
  });

  it("uses crypto.randomUUID when the context provides it", () => {
    expect(newId()).toMatch(UUID_V4);
  });
});
