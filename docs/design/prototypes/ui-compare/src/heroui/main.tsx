import "./heroui.css";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import type { Key } from "@heroui/react";
import {
  Alert, Button, Chip, ComboBox, Description, Drawer, Input, Label, ListBox, Select, Table, Tag, TagGroup,
  TextArea, TextField, ToggleButton, ToggleButtonGroup,
} from "@heroui/react";
import { Plus, Trash2 } from "lucide-react";
import { DATASETS, KINDS, OPERATORS, datasetOf, formatNumber, kindLabel } from "../shared/model";
import { Sparkline, useMetricForm } from "../shared/useMetricForm";

interface Opt { id: string; label: string; hint?: string }

/** HeroUI v3 Select written once for the many simple pickers in the form. */
function Pick({ label, value, onChange, options, placeholder, description, className, allowClear }: {
  label?: string; value: string | null; onChange: (v: string | null) => void; options: Opt[]; placeholder?: string;
  description?: React.ReactNode; className?: string; allowClear?: boolean;
}) {
  const all = allowClear ? [{ id: "__none", label: placeholder ?? "不选" }, ...options] : options;
  return (
    <Select className={className} placeholder={placeholder} value={value ?? (allowClear ? "__none" : null)}
      onChange={(k: Key | null) => onChange(k == null || k === "__none" ? null : String(k))}>
      {label && <Label>{label}</Label>}
      <Select.Trigger>
        <Select.Value />
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox>
          {all.map((o) => (
            <ListBox.Item key={o.id} id={o.id} textValue={o.label}>
              {o.label}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
      {description && <Description>{description}</Description>}
    </Select>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="flex flex-col gap-4 border-b border-separator py-5 first:pt-0 last:border-0">
    <h3 className="text-sm font-semibold">{title}</h3>
    {children}
  </section>
);

function App() {
  const m = useMetricForm();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const { form } = m;
  const showColumn = form.kind !== "count" && form.kind !== "ratio" && form.kind !== "expression";

  return (
    <div className="mx-auto max-w-[1180px] p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">语义视图 · 指标</h1>
          <p className="text-sm text-muted">HeroUI v3（Tailwind v4）</p>
        </div>
        <Button variant="primary" onPress={() => setOpen(true)}><Plus size={16} />新建指标</Button>
      </header>

      <Table>
        <Table.ScrollContainer>
          <Table.Content aria-label="指标列表">
            <Table.Header>
              <Table.Column isRowHeader>指标</Table.Column>
              <Table.Column>数据集</Table.Column>
              <Table.Column>计算方式</Table.Column>
              <Table.Column>列</Table.Column>
              <Table.Column>时间字段</Table.Column>
              <Table.Column>说明</Table.Column>
            </Table.Header>
            <Table.Body>
              {m.metrics.map((x) => (
                <Table.Row key={x.id} id={x.id}>
                  <Table.Cell><span className="font-medium">{x.name}</span></Table.Cell>
                  <Table.Cell>{datasetOf(x.datasetId)?.name}</Table.Cell>
                  <Table.Cell><Chip size="sm">{kindLabel(x.kind)}</Chip></Table.Cell>
                  <Table.Cell><code className="text-xs">{x.column ?? "—"}</code></Table.Cell>
                  <Table.Cell>{x.timeField ?? "不按时间"}</Table.Cell>
                  <Table.Cell><span className="text-muted">{x.description}</span></Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Content>
        </Table.ScrollContainer>
      </Table>

      <Drawer>
        <Drawer.Backdrop isOpen={open} onOpenChange={setOpen}>
          <Drawer.Content placement="right">
            <Drawer.Dialog className="w-[760px] max-w-full">
              <Drawer.Header>
                <Drawer.Heading>新建指标</Drawer.Heading>
              </Drawer.Header>
              <Drawer.Body>
                <Section title="基本信息">
                  <div className="grid grid-cols-2 gap-4">
                    <TextField isRequired value={form.name} onChange={(v) => m.patch({ name: v })}>
                      <Label>名称</Label>
                      <Input placeholder="例如：已完成订单金额" />
                    </TextField>
                    <div className="flex flex-col gap-1.5">
                      <TextField value={draft} onChange={setDraft}
                        onKeyDown={(e) => { if (e.key === "Enter") { m.addSynonym(draft); setDraft(""); } }}>
                        <Label>同义词</Label>
                        <Input placeholder="输入后回车" />
                      </TextField>
                      {form.synonyms.length > 0 && (
                        <TagGroup aria-label="同义词" onRemove={(keys) => keys.forEach((k) => m.removeSynonym(String(k)))}>
                          <TagGroup.List>
                            {form.synonyms.map((s) => <Tag key={s} id={s} textValue={s}>{s}</Tag>)}
                          </TagGroup.List>
                        </TagGroup>
                      )}
                    </div>
                  </div>
                  <TextField value={form.description} onChange={(v) => m.patch({ description: v })}>
                    <Label>说明</Label>
                    <TextArea rows={2} />
                  </TextField>
                </Section>

                <Section title="数据集与算法">
                  <ComboBox isRequired selectedKey={form.datasetId} onSelectionChange={(k) => k && m.setDataset(String(k))}>
                    <Label>数据集</Label>
                    <ComboBox.InputGroup>
                      <Input placeholder="搜索名称或表名" />
                      <ComboBox.Trigger />
                    </ComboBox.InputGroup>
                    <ComboBox.Popover>
                      <ListBox>
                        {DATASETS.map((d) => (
                          <ListBox.Item key={d.id} id={d.id} textValue={d.name}>
                            <div className="flex flex-col">
                              <span>{d.name}</span>
                              <span className="text-xs text-muted">{d.table} · {d.rowMeaning}</span>
                            </div>
                            <ListBox.ItemIndicator />
                          </ListBox.Item>
                        ))}
                      </ListBox>
                    </ComboBox.Popover>
                    {m.dataset && (
                      <Description>
                        {m.dataset.rowMeaning}
                        {m.dataset.snapshotColumn && <Chip size="sm" color="accent" className="ml-2">每日快照 · {m.dataset.snapshotColumn}</Chip>}
                      </Description>
                    )}
                  </ComboBox>

                  <div className="flex flex-col gap-1.5">
                    <Label>计算方式</Label>
                    <ToggleButtonGroup selectionMode="single" disallowEmptySelection className="flex-wrap"
                      selectedKeys={new Set<Key>([form.kind])}
                      onSelectionChange={(keys) => { const k = [...keys][0]; if (k) m.setKind(String(k) as typeof form.kind); }}>
                      {KINDS.map((k, i) => (
                        <ToggleButton key={k.id} id={k.id} size="sm">
                          {i > 0 && <ToggleButtonGroup.Separator />}
                          {k.label}
                        </ToggleButton>
                      ))}
                    </ToggleButtonGroup>
                  </div>

                  {showColumn && (
                    <Pick label="列" value={form.column} onChange={(v) => m.patch({ column: v })}
                      options={m.columns.map((c) => ({ id: c.name, label: `${c.comment}（${c.name}）` }))} />
                  )}

                  {form.kind === "ratio" && (
                    <div className="grid grid-cols-2 gap-4">
                      {(["numeratorId", "denominatorId"] as const).map((key) => {
                        const picked = m.metricById(form[key]);
                        return (
                          <Pick key={key} label={key === "numeratorId" ? "分子" : "分母"} value={form[key]}
                            onChange={(v) => m.patch({ [key]: v })} placeholder="选择同一数据集上的指标"
                            description={picked && `时间口径：${picked.timeField ?? "不按时间"}`}
                            options={m.components.map((x) => ({ id: x.id, label: x.name }))} />
                        );
                      })}
                    </div>
                  )}

                  {form.kind === "expression" && (
                    <TextField isRequired value={form.expression} onChange={(v) => m.patch({ expression: v })}>
                      <Label>表达式</Label>
                      <TextArea rows={3} className="font-mono" placeholder="SUM(CASE WHEN status = '已完成' THEN amount END)" />
                      <Description>只能引用所选数据集的列</Description>
                    </TextField>
                  )}
                </Section>

                {form.kind !== "ratio" && (
                  <Section title="条件">
                    {form.conditions.length === 0 && <p className="text-sm text-muted">没有条件，统计全部行</p>}
                    {form.conditions.map((c) => (
                      <div key={c.id} className="grid grid-cols-[180px_120px_1fr_40px] items-end gap-2">
                        <Pick value={c.column} onChange={(v) => m.updateCondition(c.id, { column: v ?? "" })}
                          options={(m.dataset?.columns ?? []).map((col) => ({ id: col.name, label: col.comment }))} />
                        <Pick value={c.operator} onChange={(v) => m.updateCondition(c.id, { operator: v as typeof c.operator })}
                          options={OPERATORS.map((o) => ({ id: o.id, label: o.label }))} />
                        <TextField aria-label="值" value={c.value} isDisabled={c.operator === "is_null" || c.operator === "not_null"}
                          onChange={(v) => m.updateCondition(c.id, { value: v })}>
                          <Input placeholder={c.operator === "in" ? "多个值用逗号分隔" : c.operator === "between" ? "起, 止" : "值"} />
                        </TextField>
                        <Button isIconOnly variant="ghost" aria-label="删除条件" onPress={() => m.removeCondition(c.id)}><Trash2 size={15} /></Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" className="self-start" onPress={m.addCondition}><Plus size={15} />添加条件</Button>
                  </Section>
                )}

                {form.kind !== "ratio" && (
                  <Section title="时间">
                    <Pick label="时间字段" allowClear placeholder="不按时间" value={form.timeField} onChange={(v) => m.patch({ timeField: v })}
                      options={m.dates.map((c) => ({ id: c.name, label: `${c.comment}（${c.name}）` }))}
                      description={m.dataset?.snapshotColumn
                        ? `该数据集是每日快照：按 ${m.dataset.snapshotColumn} 时每个周期取最后一天；选其他字段或不选时只取最新一天`
                        : "决定按哪个日期把数据归到周期；不选则不按时间"} />
                  </Section>
                )}

                <Section title="SQL 参考">
                  {"sql" in m.sql
                    ? <pre className="overflow-auto rounded-xl bg-default p-3 font-mono text-[13px] leading-5">{m.sql.sql}</pre>
                    : <Alert status="accent"><Alert.Indicator /><Alert.Content><Alert.Title>{m.sql.reason}</Alert.Title></Alert.Content></Alert>}
                </Section>

                <Section title="数值预览">
                  {m.result.ok ? (
                    <div className="flex items-center gap-8 rounded-xl border border-border p-4">
                      <div>
                        <div className="text-xs text-muted">{form.timeField ? "全部周期" : "当前值"}</div>
                        <div className="text-3xl font-semibold">{formatNumber(m.result.total)}</div>
                      </div>
                      {m.result.trend && m.result.trend.length > 1 ? (
                        <div className="text-accent">
                          <Sparkline points={m.result.trend} />
                          <div className="flex justify-between text-xs text-muted">
                            {m.result.trend.map((p) => <span key={p.month}>{p.month.slice(5)}月 {formatNumber(p.value)}</span>)}
                          </div>
                        </div>
                      ) : <p className="text-sm text-muted">选择时间字段后显示按月趋势</p>}
                    </div>
                  ) : (
                    <Alert status="warning"><Alert.Indicator /><Alert.Content><Alert.Title>无法预览：{m.result.reason}</Alert.Title></Alert.Content></Alert>
                  )}
                </Section>
              </Drawer.Body>
              <Drawer.Footer>
                <Button variant="secondary" onPress={() => { m.reset(); setOpen(false); }}>取消</Button>
                <Button variant="primary" isDisabled={!m.canSave} onPress={() => m.save() && setOpen(false)}>保存为提案</Button>
              </Drawer.Footer>
            </Drawer.Dialog>
          </Drawer.Content>
        </Drawer.Backdrop>
      </Drawer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
