import { describe, expect, it } from "vitest";
import { fieldLabel } from "./elementMeta";

describe("fieldLabel", () => {
  it("names the identifier and the display name differently for every kind, datasets included", () => {
    expect(fieldLabel("name")).toBe("英文标识");
    expect(fieldLabel("display_name")).toBe("名称");
    expect(fieldLabel("source_kind")).toBe("来源方式");
    expect(fieldLabel("unknown_field")).toBe("unknown_field");
  });
});
