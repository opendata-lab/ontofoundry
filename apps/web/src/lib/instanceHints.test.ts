import { expect, it } from "vitest";
import { databaseTypeHints, documentGapHints, valueMatches } from "./instanceHints";

const customerNo = {
  name: "客户编号", technical_name: "customer_no", value_kind: "string", identifier: true,
};

it("names a property whose live rows have another type", () => {
  const hints = databaseTypeHints([customerNo], { customer_no: "id" }, [{ customer_no: 1 }, { customer_no: 2 }]);
  expect(hints).toEqual([
    "客户编号：本体定义为「文本」，数据中为「整数」（本页 2 行）。可在「属性」中调整类型。",
  ]);
  expect(
    databaseTypeHints([{ ...customerNo, value_kind: "integer" }], { customer_no: "id" }, [{ customer_no: 1 }]),
  ).toEqual([]);
});

it("counts document facts that are missing a key value", () => {
  expect(
    documentGapHints([customerNo], [{ values: {} }, { values: { customer_no: " " } }, { values: { customer_no: "C1" } }]),
  ).toEqual(["客户编号 待补全：2 个实例的原文未提供该值。"]);
});

it("accepts the date forms documents use", () => {
  expect(valueMatches("datetime", "2026-01-20 10:12")).toBe(true);
  expect(valueMatches("datetime", "2026-01-20")).toBe(true);
  expect(valueMatches("datetime", "2026/01/20")).toBe(false);
});
