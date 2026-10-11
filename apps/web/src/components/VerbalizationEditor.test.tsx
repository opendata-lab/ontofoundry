import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VerbalizationEditor } from "./VerbalizationEditor";
import { valueConcept } from "../lib/verbalization";

afterEach(cleanup);

describe("语义描述", () => {
  it("treats an empty list as the generated reading, not as missing data", () => {
    const onChange = vi.fn();
    render(
      <VerbalizationEditor
        label="语义描述"
        concepts={["supplier", "material"]}
        value={[]}
        onChange={onChange}
      />,
    );
    expect(screen.getByText(/按业务名称生成标准语义描述/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "自定义语义描述" }));
    expect(onChange).toHaveBeenCalledWith([""]);
  });

  it("edits, adds and restores the generated reading", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <VerbalizationEditor
        label="语义描述"
        concepts={["supplier", "material"]}
        value={["{supplier}供应{material}"]}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "语义描述 1" }), {
      target: { value: "{supplier}向本企业供应{material}" },
    });
    expect(onChange).toHaveBeenLastCalledWith([
      "{supplier}向本企业供应{material}",
    ]);

    fireEvent.click(screen.getByRole("button", { name: /添加一句/ }));
    expect(onChange).toHaveBeenLastCalledWith([
      "{supplier}供应{material}",
      "",
    ]);

    fireEvent.click(screen.getByRole("button", { name: /恢复默认/ }));
    expect(onChange).toHaveBeenLastCalledWith([]);

    rerender(
      <VerbalizationEditor
        label="语义描述"
        concepts={["supplier", "material"]}
        value={["一", "二"]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "删除语义描述 1" }));
    expect(onChange).toHaveBeenLastCalledWith(["二"]);
  });

  it("names the value concept an attribute reading may reference", () => {
    const base = {
      technical_name: "material_code",
      value_kind: "string",
      identifier: false,
      value_concept: null,
    };
    expect(valueConcept("material", base)).toBe("String");
    expect(valueConcept("material", { ...base, value_kind: "decimal" })).toBe(
      "Decimal",
    );
    // Identifiers compile behind a generated value concept…
    expect(valueConcept("material", { ...base, identifier: true })).toBe(
      "material_material_code_value",
    );
    // …unless the model already carries an imported concept name.
    expect(
      valueConcept("material", {
        ...base,
        identifier: true,
        value_concept: "sku",
      }),
    ).toBe("sku");
    expect(
      valueConcept("material", {
        ...base,
        target_role_name: "code_role",
      }),
    ).toBe("String:code_role");
    expect(
      valueConcept("material", {
        ...base,
        identifier: true,
        value_concept: "sku",
        target_role_name: "code_role",
      }),
    ).toBe("sku:code_role");
  });
});
