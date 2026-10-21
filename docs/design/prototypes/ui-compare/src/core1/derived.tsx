import { useState } from "react";
import { Button, Input, InputNumber, Popover, Segmented, Select, Table, Tag, Tree, Typography } from "antd";
import { Plus, Trash2 } from "lucide-react";
import { mount } from "./shell";

const { Text, Title } = Typography;

// ---- Fictional ontology ------------------------------------------------------------

const PROPS = [
  { id: "region", name: "地区", type: "string" },
  { id: "age", name: "年龄", type: "integer" },
  { id: "level", name: "会员等级", type: "string" },
] as const;
/** Links that start from 人员; a reverse link reads from the other side. */
const LINKS = [
  { id: "earns", name: "薪酬", via: "领取" },
  { id: "managed_by", name: "上级", via: "被管理" },
] as const;

const OBJECTS = [
  { key: "person", title: "人员", children: [
    { key: "adult", title: "成年人", children: [{ key: "east_adult", title: "东区成年人" }] },
    { key: "employee", title: "员工" },
  ] },
];
const NAMES: Record<string, string> = { person: "人员", adult: "成年人", employee: "员工", east_adult: "东区成年人" };
const READONLY: Record<string, { parent?: string; rule: string }> = {
  person: { rule: "根对象，实例由数据绑定决定" },
  adult: { parent: "人员", rule: "年龄 大于等于 18" },
  employee: { parent: "人员", rule: "有 关联的 薪酬" },
};

interface Person { id: string; age: number; region: string; level: string; earns: boolean; managed_by: boolean }
const PEOPLE: Person[] = [
  { id: "P1", age: 20, region: "东区", level: "金卡", earns: true, managed_by: true },
  { id: "P2", age: 17, region: "东区", level: "普通", earns: false, managed_by: false },
  { id: "P3", age: 30, region: "西区", level: "金卡", earns: true, managed_by: true },
  { id: "P4", age: 45, region: "东区", level: "普通", earns: false, managed_by: true },
];

// ---- Conditions: one level, all must hold ------------------------------------------

type Op = "eq" | "neq" | "in" | "gte" | "lte" | "has" | "has_not";
interface Cond { id: string; field: string; op: Op; value: string }

const PROP_OPS: { value: Op; label: string }[] = [
  { value: "eq", label: "等于" }, { value: "neq", label: "不等于" }, { value: "in", label: "属于" },
  { value: "gte", label: "大于等于" }, { value: "lte", label: "小于等于" },
];
const LINK_OPS: { value: Op; label: string }[] = [{ value: "has", label: "有" }, { value: "has_not", label: "没有" }];

const isLink = (field: string) => LINKS.some((l) => l.id === field);
let seq = 0;
const nid = () => `c${++seq}`;

function holds(p: Person, c: Cond): boolean {
  if (isLink(c.field)) {
    const has = p[c.field as "earns" | "managed_by"];
    return c.op === "has" ? has : !has;
  }
  const v = String(p[c.field as "region" | "age" | "level"]);
  const t = c.value.trim();
  if (!t) return false;
  switch (c.op) {
    case "eq": return v === t;
    case "neq": return v !== t;
    case "in": return t.split(/[,，]/).map((x) => x.trim()).includes(v);
    case "gte": return Number(v) >= Number(t);
    case "lte": return Number(v) <= Number(t);
    default: return false;
  }
}

function Row({ c, first, onChange, onRemove }: { c: Cond; first: boolean; onChange: (c: Cond) => void; onRemove: () => void }) {
  const link = isLink(c.field);
  const prop = PROPS.find((p) => p.id === c.field);
  return (
    <div className="grid grid-cols-[40px_160px_110px_1fr_32px] items-center gap-2">
      <Text type="secondary" className="text-right">{first ? "当" : "并且"}</Text>
      <Select value={c.field} onChange={(field) => onChange({ id: c.id, field, op: isLink(field) ? "has" : "eq", value: "" })}
        options={[
          { label: "属性", options: PROPS.map((p) => ({ value: p.id, label: p.name })) },
          { label: "关联", options: LINKS.map((l) => ({ value: l.id, label: `${l.name}（${l.via}）` })) },
        ]} />
      <Select value={c.op} onChange={(op) => onChange({ ...c, op })} options={link ? LINK_OPS : PROP_OPS} />
      {link ? <Text type="secondary">关联的{LINKS.find((l) => l.id === c.field)!.name}</Text>
        : prop?.type === "integer" && c.op !== "in"
          ? <InputNumber className="!w-full" value={c.value === "" ? null : Number(c.value)} onChange={(v) => onChange({ ...c, value: v == null ? "" : String(v) })} />
          : <Input value={c.value} onChange={(e) => onChange({ ...c, value: e.target.value })} placeholder={c.op === "in" ? "多个值用逗号分隔，如 东区, 北区" : "值"} />}
      <Button type="text" icon={<Trash2 size={15} />} onClick={onRemove} aria-label="删除条件" />
    </div>
  );
}

// ---- Page --------------------------------------------------------------------------

function App() {
  const [selected, setSelected] = useState("east_adult");
  const [mode, setMode] = useState<"simple" | "expression">("simple");
  const [conds, setConds] = useState<Cond[]>([{ id: nid(), field: "region", op: "eq", value: "东区" }]);
  const [expression, setExpression] = useState("person.region = '东区' OR EXISTS (person.earns)");

  const ro = READONLY[selected];
  const members = PEOPLE.filter((p) => p.age >= 18 && conds.length > 0 && conds.every((c) => holds(p, c)));

  return (
    <div className="mx-auto grid max-w-[1100px] grid-cols-[200px_1fr] gap-8 p-6">
      <aside>
        <Text type="secondary" className="text-xs">对象</Text>
        <Tree className="mt-2 !bg-transparent" defaultExpandAll selectedKeys={[selected]} treeData={OBJECTS}
          onSelect={(k) => k[0] && setSelected(String(k[0]))} />
      </aside>

      {ro ? (
        <main className="flex flex-col gap-3">
          <Title level={4} className="!m-0">{NAMES[selected]}</Title>
          {ro.parent && <Text type="secondary">父对象：{ro.parent}</Text>}
          <div className="rounded-md bg-surface-soft px-4 py-3">{ro.rule}</div>
          <Text type="secondary" className="text-xs">原型只编辑“东区成年人”</Text>
        </main>
      ) : (
        <main className="flex flex-col gap-5">
          <div className="flex items-start justify-between">
            <div>
              <Title level={4} className="!m-0">东区成年人</Title>
              <Text type="secondary">父对象：成年人（继承条件：年龄 大于等于 18）</Text>
            </div>
            <Segmented value={mode} onChange={(v) => setMode(v as typeof mode)}
              options={[{ value: "simple", label: "按条件" }, { value: "expression", label: "写表达式" }]} />
          </div>

          <section className="flex flex-col gap-3">
            <Text strong>哪些成年人属于东区成年人</Text>
            {mode === "simple" ? (
              <>
                {conds.length === 0 && <Text type="secondary">还没有条件。没有条件时这个对象没有实例，不会等于全部成年人。</Text>}
                {conds.map((c, i) => (
                  <Row key={c.id} c={c} first={i === 0}
                    onChange={(nc) => setConds(conds.map((x) => (x.id === c.id ? nc : x)))}
                    onRemove={() => setConds(conds.filter((x) => x.id !== c.id))} />
                ))}
                <Button type="dashed" icon={<Plus size={15} />} className="ml-12 self-start"
                  onClick={() => setConds([...conds, { id: nid(), field: "level", op: "eq", value: "" }])}>添加条件</Button>
                <Text type="secondary" className="ml-12 text-xs">所有条件同时满足。不同字段之间要“或”时，切换到“写表达式”。</Text>
              </>
            ) : (
              <>
                <Input.TextArea rows={4} className="font-mono" value={expression} onChange={(e) => setExpression(e.target.value)} />
                <Text type="secondary" className="text-xs">引用父对象的属性和关联；有关联写 EXISTS (person.earns)。</Text>
              </>
            )}
          </section>

          {mode === "simple" && (
            <div className="flex items-center gap-2 border-t border-rule-soft pt-4 text-sm">
              <Text>当前满足 <Text strong>{members.length}</Text> 个人员</Text>
              {members.length > 0 && <Text type="secondary">（{members.map((p) => p.id).join("、")}）</Text>}
              <Popover trigger="click" placement="bottomLeft" content={
                <Table size="small" pagination={false} rowKey="id" dataSource={PEOPLE} columns={[
                  { title: "人员", dataIndex: "id" }, { title: "年龄", dataIndex: "age" }, { title: "地区", dataIndex: "region" },
                  { title: "会员等级", dataIndex: "level" },
                  { title: "有薪酬", dataIndex: "earns", render: (v: boolean) => (v ? "是" : "否") },
                  { title: "", render: (_: unknown, p: Person) => (members.includes(p) ? <Tag color="success">属于</Tag> : <Tag>不属于</Tag>) },
                ]} />
              }>
                <Button type="link" size="small">查看</Button>
              </Popover>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button>取消</Button>
            <Button type="primary" disabled={mode === "simple" && conds.length === 0}>保存为提案</Button>
          </div>
        </main>
      )}
    </div>
  );
}

mount(<App />);
