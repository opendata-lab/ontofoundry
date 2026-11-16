import { Alert, Button, Empty, Form, Input, Modal, Popover, Select, Table, Typography } from "antd";
import { Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, modelingApi } from "../api/client";
import type {
  AffectedItem,
  Draft,
  ModelingSession,
  Rule,
  SessionElementSave,
  SessionElementSaveImpact,
  SessionElementSavePreview,
  ValueKind,
  ValueType,
  Workspace,
} from "../api/types";
import { useElementDetail } from "../hooks/useElementDetail";
import { getWorkspacePermissions } from "../hooks/useWorkspacePermissions";
import { VALUE_KINDS } from "../lib/coreModel";
import { notifyOntologySaved } from "../lib/elementInspector";
import { newId } from "../lib/id";
import { valueTypeRules, valueTypeUsages } from "../lib/valueTypes";

const { Text } = Typography;

type Baseline = {
  sessionId: string;
  revision: number;
  draft: Draft;
};
type Editing = {
  type: ValueType;
  constraints: { id: string; expression: string }[];
  isNew: boolean;
  baseline: Baseline;
};
type AffectedState = {
  sessionId: string;
  signature: string;
  payload: SessionElementSavePreview;
  items: SessionElementSaveImpact["affected_items"];
};
type PendingSave = {
  candidateSignature: string;
  fullSignature: string;
  sessionId: string;
  payload: SessionElementSave;
};

/** Shared value domains: everything shows in the row; create and edit use a dialog. */
export function ValueTypeCatalog({ workspace, draft, sessionId, query, createRequest, onSaved }: {
  workspace: Workspace;
  draft: Draft;
  sessionId: string | null;
  query: string;
  /** Incremented by the page toolbar's “新建值类型” button. */
  createRequest: number;
  onSaved: (session: ModelingSession) => void;
}) {
  const detail = useElementDetail();
  const { canEdit } = getWorkspacePermissions(workspace);
  const [editing, setEditing] = useState<Editing | null>(null);
  const editingRef = useRef<Editing | null>(null);
  const [affected, setAffected] = useState<AffectedState | null>(null);
  const [opening, setOpening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const openSeq = useRef(0);
  const pendingSave = useRef<PendingSave | null>(null);
  const words = query.trim().toLowerCase();
  const rows = (draft.value_types ?? []).filter((v) =>
    !words || [v.display_name ?? "", v.name, v.description, ...valueTypeRules(draft, v.id).map((r) => r.expression)].join(" ").toLowerCase().includes(words));

  useEffect(() => () => {
    openSeq.current++;
  }, []);

  const open = async (type?: ValueType) => {
    const seq = ++openSeq.current;
    setError("");
    setLoadError("");
    setAffected(null);
    pendingSave.current = null;
    setOpening(true);
    try {
      const session = sessionId
        ? await modelingApi.get(workspace.id, sessionId)
        : await modelingApi.personal(workspace.id);
      if (seq !== openSeq.current) return;
      const baseline: Baseline = {
        sessionId: session.id,
        revision: session.revision,
        draft: session.draft,
      };
      if (type) {
        const currentType = (session.draft.value_types ?? []).find((v) => v.id === type.id);
        if (!currentType) {
          setLoadError("该值类型在当前草稿中已不存在");
          return;
        }
        const next: Editing = {
          type: { ...currentType },
          constraints: valueTypeRules(session.draft, currentType.id).map((r) => ({ id: r.id, expression: r.expression })),
          isNew: false,
          baseline,
        };
        editingRef.current = next;
        setEditing(next);
      } else {
        const next: Editing = {
          type: { id: newId(), name: "", display_name: "", description: "", value_kind: "string", evidence: [] },
          constraints: [{ id: newId(), expression: "" }],
          isNew: true,
          baseline,
        };
        editingRef.current = next;
        setEditing(next);
      }
    } catch (e) {
      if (seq === openSeq.current) {
        setLoadError(e instanceof Error ? e.message : "读取草稿失败");
      }
    } finally {
      if (seq === openSeq.current) setOpening(false);
    }
  };
  const updateEditing = (next: Editing) => {
    editingRef.current = next;
    pendingSave.current = null;
    setAffected(null);
    setEditing(next);
  };
  const closeEditor = () => {
    if (busy) return;
    openSeq.current++;
    editingRef.current = null;
    pendingSave.current = null;
    setAffected(null);
    setError("");
    setEditing(null);
  };
  const handled = useRef(createRequest);
  useEffect(() => {
    if (createRequest === handled.current) return;
    handled.current = createRequest;
    void open();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open reads current props only
  }, [createRequest]);
  const candidate = (current: Editing, baseDraft: Draft): Draft => {
    const { type } = current;
    const existing = new Map(valueTypeRules(baseDraft, type.id).map((r) => [r.id, r]));
    const rules: Rule[] = current.constraints
      .filter((c) => c.expression.trim())
      .map((c, index) => ({
        ...(existing.get(c.id) ?? { description: "", evidence: [], display_name: null }),
        id: c.id,
        name: existing.get(c.id)?.name ?? `${type.name}_rule_${index + 1}`,
        owner_kind: "value_type",
        owner_id: type.id,
        rule_kind: "constraint",
        expression: c.expression.trim(),
      }));
    // Properties referencing the type follow its base kind (VT-09: revised together).
    const properties = baseDraft.properties.map((p) => (p.value_type_id === type.id ? { ...p, value_kind: type.value_kind } : p));
    return {
      ...baseDraft,
      value_types: [...(baseDraft.value_types ?? []).filter((v) => v.id !== type.id), { ...type, display_name: type.display_name?.trim() || null }],
      rules: [...baseDraft.rules.filter((r) => !(r.owner_kind === "value_type" && r.owner_id === type.id)), ...rules],
      properties,
    };
  };
  const buildCandidate = (current: Editing) => {
    const payload: SessionElementSavePreview = {
      target_kind: "value_type",
      target_id: current.type.id,
      expected_session_revision: current.baseline.revision,
      draft: candidate(current, current.baseline.draft),
    };
    return {
      sessionId: current.baseline.sessionId,
      payload,
      signature: JSON.stringify({ sessionId: current.baseline.sessionId, ...payload }),
    };
  };
  const sendSaveRequest = async (
    targetSessionId: string,
    requestPayload: SessionElementSave,
    candidateSignature: string,
    fullSignature: string,
  ) => {
    pendingSave.current = {
      candidateSignature,
      fullSignature,
      sessionId: targetSessionId,
      payload: requestPayload,
    };
    try {
      const result = await modelingApi.saveElement(workspace.id, targetSessionId, requestPayload);
      pendingSave.current = null;
      notifyOntologySaved({ workspaceId: workspace.id, session: result });
      onSaved(result);
      editingRef.current = null;
      setEditing(null);
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 408 && e.status !== 429) {
        pendingSave.current = null;
      }
      throw e;
    }
  };
  const sendSave = async (
    targetSessionId: string,
    payload: SessionElementSavePreview,
    affectedItems: AffectedItem[],
    candidateSignature: string,
  ) => {
    const savePayload = { ...payload, affected_items: affectedItems };
    const fullSignature = JSON.stringify({ sessionId: targetSessionId, ...savePayload });
    const key =
      pendingSave.current?.fullSignature === fullSignature
        ? pendingSave.current.payload.idempotency_key
        : newId();
    await sendSaveRequest(targetSessionId, { ...savePayload, idempotency_key: key }, candidateSignature, fullSignature);
  };
  const save = async () => {
    const currentEditing = editingRef.current;
    if (!currentEditing || busy) return;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(currentEditing.type.name)) {
      setError("英文标识只能使用字母、数字和下划线，且不能以数字开头");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let current = buildCandidate(currentEditing);
      if (affected && affected.signature === current.signature) {
        const affectedItems: AffectedItem[] = affected.items.map(
          ({ target_kind, target_id, expected_target_hash }) => ({
            target_kind,
            target_id,
            expected_target_hash,
          }),
        );
        setAffected(null);
        await sendSave(affected.sessionId, affected.payload, affectedItems, current.signature);
        return;
      }
      setAffected(null);
      if (
        pendingSave.current &&
        pendingSave.current.candidateSignature === current.signature &&
        pendingSave.current.sessionId === current.sessionId
      ) {
        const pending = pendingSave.current;
        await sendSaveRequest(pending.sessionId, pending.payload, pending.candidateSignature, pending.fullSignature);
        return;
      }
      while (current) {
        const requestSignature = current.signature;
        const impact = await modelingApi.previewElementSave(workspace.id, current.sessionId, current.payload);
        const latestEditing = editingRef.current;
        if (!latestEditing) return;
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(latestEditing.type.name)) {
          setAffected(null);
          setError("英文标识只能使用字母、数字和下划线，且不能以数字开头");
          return;
        }
        const latest = buildCandidate(latestEditing);
        if (latest.signature !== requestSignature) {
          current = latest;
          continue;
        }
        if (impact.affected_items.length) {
          setAffected({
            sessionId: latest.sessionId,
            signature: latest.signature,
            payload: latest.payload,
            items: impact.affected_items,
          });
          return;
        }
        await sendSave(latest.sessionId, latest.payload, [], latest.signature);
        return;
      }
    } catch (e) {
      setAffected(null);
      setError(e instanceof Error ? e.message : "保存值类型失败");
    } finally {
      setBusy(false);
    }
  };
  const usageCell = (type: ValueType) => {
    const used = valueTypeUsages(draft, type.id);
    if (!used.length) return <Text type="secondary">0</Text>;
    return (
      <Popover
        trigger="click"
        title={`使用「${type.display_name || type.name}」的属性`}
        content={
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {used.map((p) => {
              const owner = draft.object_types.find((o) => o.id === p.owner_type_id);
              return (
                <li key={p.id}>
                  <Link to={detail.href({ kind: "object_type", id: p.owner_type_id, tab: "properties", sessionId })}>
                    {(owner?.display_name || owner?.name) ?? "?"} · {p.display_name || p.name}
                  </Link>
                </li>
              );
            })}
          </ul>
        }
      >
        <Button type="link" size="small" className="h-auto p-0" aria-label={`查看使用 ${type.name} 的属性`}>{used.length}</Button>
      </Popover>
    );
  };
  return (
    <>
      {loadError && <Alert type="error" showIcon message={loadError} className="mb-3" />}
      <Table<ValueType>
        size="middle"
        rowKey="id"
        dataSource={rows}
        onHeaderRow={() => ({ className: "text-xs" })}
        pagination={rows.length > 20 ? { pageSize: 20 } : false}
        locale={{ emptyText: <Empty description={(draft.value_types ?? []).length ? "没有匹配的值类型" : "还没有值类型定义"} /> }}
        columns={[
          {
            title: "名称", key: "name", render: (_, v) => canEdit
              ? <Button type="link" className="h-auto p-0 font-medium" disabled={opening} onClick={() => void open(v)}>{v.display_name || v.name}</Button>
              : <span className="font-medium">{v.display_name || v.name}</span>,
          },
          { title: "英文标识", key: "identifier", render: (_, v) => <code className="text-xs whitespace-nowrap">{v.name}</code> },
          { title: "基础类型", key: "kind", render: (_, v) => <span className="whitespace-nowrap">{VALUE_KINDS[v.value_kind]}</span> },
          {
            title: "约束", key: "constraints", render: (_, v) => {
              const rules = valueTypeRules(draft, v.id);
              return rules.length ? <span className="flex flex-col gap-1">{rules.map((r) => <code key={r.id} className="text-xs">{r.expression}</code>)}</span> : <Text type="secondary">—</Text>;
            },
          },
          { title: "使用属性", key: "usage", render: (_, v) => usageCell(v) },
          {
            title: "描述", key: "description", render: (_, v) => v.description
              ? <Text type="secondary" className="block max-w-sm truncate text-xs" title={v.description}>{v.description}</Text>
              : <Text type="secondary">—</Text>,
          },
        ]}
      />
      {editing && (
        <Modal
          open
          title={editing.isNew ? "新建值类型" : `编辑值类型：${editing.type.display_name || editing.type.name}`}
          okText={affected ? "确认并保存" : "保存"}
          cancelText="取消"
          okButtonProps={{ loading: busy }}
          onCancel={closeEditor}
          onOk={() => void save()}
        >
          <Form layout="vertical" component="div">
            <Form.Item label="名称"><Input aria-label="值类型名称" value={editing.type.display_name ?? ""} placeholder="例如：会员等级" onChange={(e) => updateEditing({ ...editing, type: { ...editing.type, display_name: e.target.value } })} /></Form.Item>
            <Form.Item label="英文标识" required><Input aria-label="值类型英文标识" value={editing.type.name} placeholder="例如：member_level" onChange={(e) => updateEditing({ ...editing, type: { ...editing.type, name: e.target.value } })} /></Form.Item>
            <Form.Item label="基础类型" required extra={valueTypeUsages(editing.baseline.draft, editing.type.id).length ? "修改基础类型会同步修改使用它的属性" : undefined}>
              <Select aria-label="基础类型" value={editing.type.value_kind} options={(Object.keys(VALUE_KINDS) as ValueKind[]).map((k) => ({ value: k, label: VALUE_KINDS[k] }))} onChange={(k: ValueKind) => updateEditing({ ...editing, type: { ...editing.type, value_kind: k } })} />
            </Form.Item>
            <Form.Item label="约束" extra={`用英文标识表示当前值，例如 ${editing.type.name || "member_level"} IN ('普通', '金卡')；只约束有值时的取值，是否必填在属性上设置`}>
              <div className="flex flex-col gap-2">
                {editing.constraints.map((c, index) => (
                  <div key={c.id} className="flex items-center gap-2">
                    <Input aria-label={`约束 ${index + 1}`} value={c.expression} onChange={(e) => updateEditing({ ...editing, constraints: editing.constraints.map((x) => (x.id === c.id ? { ...x, expression: e.target.value } : x)) })} />
                    <Button type="text" aria-label={`删除约束 ${index + 1}`} icon={<Minus size={14} />} onClick={() => updateEditing({ ...editing, constraints: editing.constraints.filter((x) => x.id !== c.id) })} />
                  </div>
                ))}
                <div><Button size="small" icon={<Plus size={14} />} onClick={() => updateEditing({ ...editing, constraints: [...editing.constraints, { id: newId(), expression: "" }] })}>添加约束</Button></div>
              </div>
            </Form.Item>
            <Form.Item label="描述"><Input.TextArea aria-label="值类型描述" rows={2} value={editing.type.description} onChange={(e) => updateEditing({ ...editing, type: { ...editing.type, description: e.target.value } })} /></Form.Item>
          </Form>
          {affected && (
            <Alert type="warning" showIcon message={`保存会同时影响 ${affected.items.length} 个元素`} description={<ul className="m-0 pl-4">{affected.items.map((a) => <li key={a.target_id}>{a.reason}</li>)}</ul>} />
          )}
          {error && <Alert type="error" showIcon message={error} />}
        </Modal>
      )}
    </>
  );
}
