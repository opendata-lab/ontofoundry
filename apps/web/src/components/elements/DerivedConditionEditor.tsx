import { Alert, Button, Form, Input, Segmented, Select, Typography } from "antd";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { DerivedBranch, Draft, ObjectType, Operator } from "../../api/types";
import { byId } from "../../lib/coreModel";
import {
  OPERATORS,
  branchSummary,
  branchesText,
  branchesFromForm,
  derivedContext,
  formErrors,
  formFromBranches,
  newLinkRow,
  newPropertyRow,
  operatorsFor,
  type DerivedForm,
  type DerivedRow,
} from "../../lib/derivedEditing";
import { ConditionValueInput } from "./ConditionValueInput";

const { Text } = Typography;

/** Read-only membership summary: one line per branch, OR between them. */
export function DerivedSummary({ draft, object }: { draft: Draft; object: ObjectType }) {
  if (!object.derived_by.length) return <Text type="secondary">没有本层成员条件</Text>;
  return (
    <div className="flex flex-col gap-1">
      {object.derived_by.map((branch, i) => (
        <div key={i} className="rounded-sm bg-surface-soft px-3 py-2 text-sm">
          {i > 0 && <Text type="secondary">或者 </Text>}
          {branch.kind === "expression" ? <code>{branch.expression}</code> : branchSummary(draft, branch)}
        </div>
      ))}
    </div>
  );
}

/**
 * Which parent instances belong to this child. One level of conditions that
 * all hold; "or" or deeper paths switch to an expression.
 */
export function DerivedConditionEditor({
  draft,
  object,
  onChange,
}: {
  draft: Draft;
  object: ObjectType;
  onChange: (branches: DerivedBranch[]) => void;
}) {
  const context = derivedContext(draft, object.extends);
  const [form, setForm] = useState<DerivedForm>(() => formFromBranches(draft, object.extends, object.derived_by));
  const update = (next: DerivedForm) => {
    setForm(next);
    onChange(branchesFromForm(draft, object.extends, next));
  };
  const errors = formErrors(draft, form);
  const parentName = context.parent?.name ?? "父对象";
  const fieldValue = (row: DerivedRow) =>
    row.kind === "property" ? `p:${row.propertyId}` : `l:${row.linkId}:${row.direction}`;
  const fieldOptions = [
    {
      label: "属性",
      options: context.properties.map((p) => ({ value: `p:${p.id}`, label: p.name })),
    },
    {
      label: "关联",
      options: context.links.map((l) => {
        const other = byId(draft.object_types, l.direction === "forward" ? l.link.target_type_id : l.link.source_type_id);
        const name = l.direction === "reverse" && l.link.inverse_name ? l.link.inverse_name : l.link.name;
        return { value: `l:${l.link.id}:${l.direction}`, label: `${name}（${other?.name ?? "?"}）` };
      }),
    },
  ];
  const setRow = (key: string, row: DerivedRow) =>
    form.mode === "simple" && update({ ...form, rows: form.rows.map((r) => (r.key === key ? row : r)) });
  const changeField = (row: DerivedRow, value: string) => {
    const [kind, id, direction] = value.split(":");
    if (kind === "p") setRow(row.key, { ...newPropertyRow(byId(draft.properties, id)), key: row.key });
    else {
      const link = context.links.find((l) => l.link.id === id && l.direction === direction);
      if (link) setRow(row.key, { ...newLinkRow(link), key: row.key });
    }
  };
  if (!object.extends) return null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <Text strong>哪些{parentName}属于{object.name || "这个对象"}</Text>
        <Segmented
          size="small"
          value={form.mode}
          onChange={(mode) => {
            if (mode === form.mode) return;
            update(
              mode === "expression"
                ? {
                    mode: "expression",
                    expression: branchesText(draft, object.extends, branchesFromForm(draft, object.extends, form)),
                  }
                : formFromBranches(draft, object.extends, branchesFromForm(draft, object.extends, form)),
            );
          }}
          options={[
            { value: "simple", label: "按条件" },
            { value: "expression", label: "写表达式" },
          ]}
        />
      </div>
      {form.mode === "simple" ? (
        <>
          {form.rows.length === 0 && (
            <Text type="secondary">还没有条件。没有条件时成员只由成员扩展表决定；两者都没有时这个对象没有实例。</Text>
          )}
          {form.rows.map((row, i) => {
            const property = row.kind === "property" ? byId(draft.properties, row.propertyId) : undefined;
            const error = errors[row.key];
            return (
              <Form.Item
                key={row.key}
                className="!mb-0 [&_.ant-form-item-explain]:pl-12 [&_.ant-form-item-explain]:text-xs"
                validateStatus={error ? "error" : undefined}
                help={error}
              >
                <div className="grid grid-cols-[40px_minmax(140px,1.2fr)_110px_minmax(160px,2fr)_32px] items-center gap-2">
                  <Text type="secondary" className="text-right">
                    {i === 0 ? "当" : "并且"}
                  </Text>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    aria-label={`条件 ${i + 1} 的字段`}
                    placeholder="属性或关联"
                    value={row.kind === "property" && !row.propertyId ? undefined : fieldValue(row)}
                    onChange={(v) => changeField(row, v)}
                    options={fieldOptions}
                  />
                  {row.kind === "link" ? (
                    <Select
                      aria-label={`条件 ${i + 1} 的判断`}
                      value={row.has ? "has" : "has_not"}
                      onChange={(v) => setRow(row.key, { ...row, has: v === "has" })}
                      options={[
                        { value: "has", label: "有" },
                        { value: "has_not", label: "没有" },
                      ]}
                    />
                  ) : (
                    <Select
                      aria-label={`条件 ${i + 1} 的运算`}
                      value={row.operator}
                      onChange={(operator: Operator) => setRow(row.key, { ...row, operator, values: [] })}
                      options={operatorsFor(property?.value_kind ?? null).map((op) => ({ value: op, label: OPERATORS[op] }))}
                    />
                  )}
                  {row.kind === "link" ? (
                    <Text type="secondary">关联的实例</Text>
                  ) : (
                    <ConditionValueInput
                      kind={property?.value_kind ?? "string"}
                      operator={row.operator}
                      values={row.values}
                      label={`条件 ${i + 1} 的值`}
                      onChange={(values) => setRow(row.key, { ...row, values })}
                    />
                  )}
                  <Button
                    type="text"
                    aria-label={`删除条件 ${i + 1}`}
                    icon={<Trash2 size={15} />}
                    onClick={() => update({ ...form, rows: form.rows.filter((r) => r.key !== row.key) })}
                  />
                </div>
              </Form.Item>
            );
          })}
          <Button
            type="dashed"
            icon={<Plus size={15} />}
            className="ml-12 self-start"
            disabled={(!context.properties.length && !context.links.length) || undefined}
            onClick={() => update({ ...form, rows: [...form.rows, newPropertyRow(context.properties[0])] })}
          >
            添加条件
          </Button>
          <Text type="secondary" className="ml-12 text-xs">
            所有条件同时满足。需要“或者”或多跳关联时，切换到“写表达式”。
          </Text>
        </>
      ) : (
        <>
          <Input.TextArea
            aria-label="成员表达式"
            rows={4}
            className="font-mono"
            value={form.expression}
            onChange={(e) => update({ mode: "expression", expression: e.target.value })}
          />
          <Text type="secondary" className="text-xs">
            从 {context.parent?.technical_name ?? "父对象"} 出发引用属性和关联，例如{" "}
            <code>{context.parent?.technical_name ?? "parent"}.属性技术名 = '值'</code>；有关联写{" "}
            <code>EXISTS ({context.parent?.technical_name ?? "parent"}.关系技术名)</code>，反向关系写{" "}
            <code>REVERSE(关系技术名)</code>。保存时由服务器校验。
          </Text>
        </>
      )}
      {!context.properties.length && !context.links.length && (
        <Alert type="info" showIcon message={`${parentName}还没有属性或关联，可以先写表达式或使用成员扩展表。`} />
      )}
    </div>
  );
}
