import { Alert, Button, Form, Input, Progress, Radio, Typography } from "antd";
import { useState } from "react";
import { ApiError, publishApi } from "../../api/client";
import type { Json, MergeConflict, ModelingSession, Resolution } from "../../api/types";
import { SectionTitle, StatusMark } from "../layout";
import { fieldLabel, KIND } from "../proposals/elementMeta";

const { Text } = Typography;

function show(value: unknown) {
  if (value === null || value === undefined) return "（无）";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

const title = (c: MergeConflict) =>
  `${c.element_kind ? `${KIND[c.element_kind].label} · ` : ""}${c.element_label} / ${
    c.kind === "delete_modify" ? "删除与修改" : fieldLabel(c.path)
  }`;

const LABELS: Record<Resolution["choice"], [string, string]> = {
  latest: ["采用当前发布版本", "保留当前发布版本的内容，放弃本会话的修改"],
  draft: ["采用本会话修改", "用本会话的修改覆盖当前发布版本"],
  custom: ["自定义", "手动编辑合并后的内容"],
  both: ["都保留", "保留两边新增的所有值"],
};

const STRING_PATHS = new Set([
  "name",
  "display_name",
  "description",
  "source_role_name",
  "target_role_name",
  "expression",
  "schema_name",
  "table_name",
  "snapshot_date_column",
  "membership_source_id",
  "extends",
  "title_property_id",
]);

function isStringConflict(c: MergeConflict): boolean {
  if (typeof c.draft === "string" || typeof c.latest === "string" || typeof c.base === "string") return true;
  if (
    (c.draft !== null && c.draft !== undefined) ||
    (c.latest !== null && c.latest !== undefined) ||
    (c.base !== null && c.base !== undefined)
  ) {
    return false;
  }
  return STRING_PATHS.has(c.path);
}

function initialCustomText(c: MergeConflict): string {
  if (isStringConflict(c)) return typeof c.draft === "string" ? c.draft : "";
  return JSON.stringify(c.draft ?? null, null, 2);
}

/**
 * One conflict at a time: session start, current published version and this
 * session's change side by side. Applying the choices saves them to the
 * session, which moves its revision, so the page previews again.
 */
export function ConflictResolver({
  conflicts,
  currentVersionId,
  session,
  onResolved,
  onOutdated,
}: {
  conflicts: MergeConflict[];
  currentVersionId: string | null;
  session: ModelingSession;
  onResolved: (session: ModelingSession) => void;
  /** The version moved again: these conflicts are no longer the right ones. */
  onOutdated: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [choices, setChoices] = useState<Record<string, Resolution>>({});
  const [customText, setCustomText] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const conflict = conflicts[Math.min(index, conflicts.length - 1)];
  const resolved = conflicts.filter((c) => choices[c.key]).length;
  const choose = (choice: Resolution["choice"]) => {
    setChoices((all) => ({ ...all, [conflict.key]: { choice } }));
    if (choice === "custom" && customText[conflict.key] === undefined)
      setCustomText((t) => ({ ...t, [conflict.key]: initialCustomText(conflict) }));
  };
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const resolutions: Record<string, Resolution> = {};
      for (const c of conflicts) {
        const r = choices[c.key];
        if (r.choice !== "custom") {
          resolutions[c.key] = r;
          continue;
        }
        const text = customText[c.key] ?? "";
        let value: Json = text;
        if (!isStringConflict(c)) {
          try {
            value = JSON.parse(text) as Json;
          } catch {
            throw new Error(`「${c.element_label} / ${c.path}」的自定义值不是有效 JSON`);
          }
        }
        resolutions[c.key] = { choice: "custom", value };
      }
      onResolved(await publishApi.resolve(session, currentVersionId, resolutions));
    } catch (e) {
      if (e instanceof ApiError && (e.code === "PREVIEW_OUTDATED" || e.code === "CONFLICTS_UNRESOLVED")) {
        onOutdated();
        return;
      }
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="review-conflicts">
        <aside className="flex flex-col gap-1" aria-label="冲突列表">
          <SectionTitle title="冲突" />
          {conflicts.map((c, i) => (
            <Button
              key={c.key}
              type={i === index ? "primary" : "text"}
              ghost={i === index}
              aria-current={i === index ? "true" : undefined}
              className="flex h-auto justify-between gap-2 py-2 text-left"
              onClick={() => setIndex(i)}
            >
              <span className="truncate">{title(c)}</span>
              <StatusMark state={choices[c.key] ? "mapped" : "partial"} label={choices[c.key] ? "已选择" : "待处理"} className="shrink-0" />
            </Button>
          ))}
        </aside>
        <section className="flex min-w-0 flex-col gap-3" aria-label="解决冲突">
          <SectionTitle title={title(conflict)} />
          <div className="grid grid-cols-3 gap-2">
            {(
              [
                ["会话起点", conflict.base],
                ["当前发布版本", conflict.latest],
                ["本会话修改", conflict.draft],
              ] as [string, unknown][]
            ).map(([label, value]) => (
              <div key={label} className="flex min-w-0 flex-col gap-1">
                <Text type="secondary" className="text-xs">
                  {label}
                </Text>
                <pre className="m-0 max-h-48 overflow-auto rounded-sm bg-surface-soft p-2 font-mono text-xs whitespace-pre-wrap">
                  {show(value)}
                </pre>
              </div>
            ))}
          </div>
          <Radio.Group
            aria-label="处理方式"
            value={choices[conflict.key]?.choice}
            onChange={(e) => choose(e.target.value as Resolution["choice"])}
            className="flex flex-col gap-2"
          >
            {conflict.allowed.map((choice) => (
              <Radio key={choice} value={choice}>
                <strong>{LABELS[choice][0]}</strong> <Text type="secondary">{LABELS[choice][1]}</Text>
              </Radio>
            ))}
          </Radio.Group>
          {choices[conflict.key]?.choice === "custom" && (
            <Form layout="vertical" component="div">
              <Form.Item label="合并后的内容" className="mb-0">
                <Input.TextArea
                  aria-label="合并后的内容"
                  className="font-mono"
                  rows={4}
                  value={customText[conflict.key] ?? ""}
                  onChange={(e) => setCustomText((t) => ({ ...t, [conflict.key]: e.target.value }))}
                />
              </Form.Item>
            </Form>
          )}
          <div className="flex gap-2">
            <Button disabled={index === 0} onClick={() => setIndex(index - 1)}>
              上一个
            </Button>
            <Button disabled={index >= conflicts.length - 1} onClick={() => setIndex(index + 1)}>
              下一个
            </Button>
          </div>
        </section>
      </div>
      <footer className="flex flex-wrap items-center gap-3 border-t border-rule pt-3">
        <StatusMark state={resolved === conflicts.length ? "mapped" : "partial"} label={`已解决 ${resolved} / ${conflicts.length}`} />
        <Progress className="m-0 w-14" percent={Math.round((100 * resolved) / conflicts.length)} size={{ height: 4 }} showInfo={false} />
        {error && <Alert type="error" showIcon message={error} />}
        <Button className="ml-auto" type="primary" loading={busy} disabled={resolved < conflicts.length} onClick={() => void submit()}>
          应用到会话并重新预览
        </Button>
      </footer>
    </div>
  );
}
