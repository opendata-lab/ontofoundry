import { Alert, Button, Collapse, Form, Input, Select, Typography } from "antd";
import { useRef, useState } from "react";
import { importApi } from "../api/client";
import type { Dataset, ImportCompletion, ImportConfirmed, ImportSource, ModelingSession } from "../api/types";
import { DIALECTS } from "../lib/datasetEditing";
import { newId } from "../lib/id";
import { StatusMark } from "./layout";

export function ImportCompletionList({ items, source, session, onChanged }: { items: ImportCompletion[]; source: ImportSource; session: ModelingSession; onChanged: (result: ImportConfirmed) => void }) {
  if (!items.length) return <Typography.Paragraph type="secondary">没有可人工补全的条目。</Typography.Paragraph>;
  return <Collapse items={items.map((item) => ({ key: item.issue_id, label: <span className="flex items-start gap-2"><StatusMark state={item.status === "accepted" ? "mapped" : item.status === "proposed" ? "pending" : "partial"} label={item.status === "accepted" ? "已接受" : item.status === "proposed" ? "待审" : "待补全"} /><span>{item.message}</span></span>, children: <CompletionEditor key={`${item.issue_id}:${session.revision}:${item.status}`} item={item} source={source} session={session} onChanged={onChanged} /> }))} />;
}

function CompletionEditor({ item, source, session, onChanged }: { item: ImportCompletion; source: ImportSource; session: ModelingSession; onChanged: (result: ImportConfirmed) => void }) {
  const [metadata, setMetadata] = useState<Dataset | null>(item.dataset ?? null);
  const [datasetId, setDatasetId] = useState<string>();
  const [definition, setDefinition] = useState(item.original ?? "{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef(newId());
  const submitting = useRef(false);
  const submit = async () => {
    if (submitting.current) return;
    setError("");
    let parsed: Record<string, unknown> | undefined;
    if (item.kind === "source_definition") {
      try {
        const value: unknown = JSON.parse(definition);
        if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("请填写一个 JSON 对象");
        parsed = value as Record<string, unknown>;
      } catch (e) { setError(e instanceof Error ? e.message : "来源定义格式有误"); return; }
    }
    submitting.current = true; setBusy(true);
    try {
      const result = await importApi.complete(session.workspace_id, source, { issue_id: item.issue_id, expected_session_revision: session.revision, expected_draft_sha256: session.draft_sha256, idempotency_key: key.current, ...(item.kind === "count_dataset" ? { dataset_id: datasetId } : item.kind === "dataset_metadata" ? { dataset: metadata } : { definition: parsed }) });
      onChanged(result);
    } catch (e) { setError(e instanceof Error ? e.message : "补全失败"); }
    finally { submitting.current = false; setBusy(false); }
  };
  return <div className="flex flex-col gap-3">
    <Typography.Text code className="break-all">{item.source_path}</Typography.Text>
    {error && <Alert type="error" showIcon message={error} />}
    {item.status === "accepted" ? <Typography.Text>修订提案已接受，历史转换报告保持原样。</Typography.Text> : <>
      <Form layout="vertical">
        {item.kind === "count_dataset" ? <Form.Item label="COUNT(*) 的统计数据集" extra="按所选数据集的行数统计；选择后仍需审阅提案。"><Select showSearch optionFilterProp="label" aria-label="统计数据集" placeholder="搜索并选择数据集" value={datasetId} disabled={busy} onChange={(id) => { setDatasetId(id); key.current = newId(); }} options={item.datasets.map((d) => ({ value: d.id, label: d.name }))} /></Form.Item> : item.kind === "dataset_metadata" && metadata ? <>
          <Form.Item label="数据集"><Typography.Text>{metadata.name}</Typography.Text></Form.Item>
          <Form.Item label="数据库方言"><Select showSearch optionFilterProp="label" aria-label="数据库方言" value={metadata.dialect ?? undefined} options={DIALECTS} disabled={busy} onChange={(dialect) => { setMetadata({ ...metadata, dialect }); key.current = newId(); }} /></Form.Item>
          {(metadata.columns ?? []).map((column, index) => <div key={index} className="mb-2 grid grid-cols-3 gap-2">
            <Input aria-label={`列名 ${index + 1}`} placeholder="物理列名" value={column.name} disabled={busy} onChange={(e) => { setMetadata({ ...metadata, columns: metadata.columns!.map((c, i) => i === index ? { ...c, name: e.target.value } : c) }); key.current = newId(); }} />
            <Input aria-label={`物理类型 ${index + 1}`} placeholder="如 BIGINT" value={column.physical_type ?? ""} disabled={busy} onChange={(e) => { setMetadata({ ...metadata, columns: metadata.columns!.map((c, i) => i === index ? { ...c, physical_type: e.target.value || null } : c) }); key.current = newId(); }} />
            <Input aria-label={`列注释 ${index + 1}`} placeholder="列注释" value={column.comment} disabled={busy} onChange={(e) => { setMetadata({ ...metadata, columns: metadata.columns!.map((c, i) => i === index ? { ...c, comment: e.target.value } : c) }); key.current = newId(); }} />
          </div>)}
          <Button disabled={busy} onClick={() => { setMetadata({ ...metadata, columns: [...(metadata.columns ?? []), { name: "", physical_type: null, comment: "" }] }); key.current = newId(); }}>补登记列</Button>
        </> : <Form.Item label="修订来源定义" extra="仅修改此条来源 JSON。系统重新转换与校验，成功后生成待审提案。"><Input.TextArea aria-label="修订来源定义" value={definition} disabled={busy} autoSize={{ minRows: 5, maxRows: 12 }} onChange={(e) => { setDefinition(e.target.value); key.current = newId(); }} /></Form.Item>}
      </Form>
      <div className="flex justify-end"><Button loading={busy} disabled={item.kind === "count_dataset" && !datasetId} onClick={() => void submit()}>生成修订提案</Button></div>
    </>}
  </div>;
}
