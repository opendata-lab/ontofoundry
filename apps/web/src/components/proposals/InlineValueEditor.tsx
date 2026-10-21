import { Alert, Button, Input, InputNumber, Select, Switch } from "antd";
import { Check, Pencil, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AGGREGATIONS, MULTIPLICITY, VALUE_KINDS } from "../../lib/coreModel";

const ENUMS: Record<string, Record<string, string>> = {
  value_kind: VALUE_KINDS,
  multiplicity: MULTIPLICITY,
  aggregation: AGGREGATIONS,
};
const LONG_TEXT = new Set(["description", "expression", "query_sql"]);

type Kind = "enum" | "boolean" | "number" | "long" | "text" | "json";

function editorKind(path: string, value: unknown): Kind {
  if (ENUMS[path]) return "enum";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "number";
  if (LONG_TEXT.has(path)) return "long";
  if (value === null || value === undefined || typeof value === "string") return "text";
  return "json";
}

/** A proposed value that shows a pencil on hover and edits in place. */
export function InlineValueEditor({ path, label, value, display, disabled, onSave }: {
  path: string;
  label: string;
  value: unknown;
  display: ReactNode;
  disabled: boolean;
  onSave: (value: unknown) => Promise<boolean>;
}) {
  const kind = editorKind(path, value);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(value);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const start = () => {
    setDraft(value);
    setText(kind === "json" ? JSON.stringify(value, null, 2) : "");
    setError("");
    setEditing(true);
  };
  const cancel = () => {
    setEditing(false);
    setError("");
  };
  const save = async () => {
    let next = draft;
    if (kind === "json") {
      try {
        next = JSON.parse(text);
      } catch {
        setError("JSON 无法解析");
        return;
      }
    }
    if (kind === "text" && next === "") next = null;
    // An empty structured field (columns, measure…) has no type to infer from; accept JSON input.
    if (kind === "text" && value == null && typeof next === "string" && /^\s*[[{]/.test(next)) {
      try {
        next = JSON.parse(next);
      } catch {
        setError("JSON 无法解析");
        return;
      }
    }
    setSaving(true);
    const ok = await onSave(next);
    setSaving(false);
    if (ok) setEditing(false);
    else setError("保存未通过，请按提示修改");
  };
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") cancel();
    if (e.key === "Enter" && kind !== "long" && kind !== "json") void save();
  };

  if (!editing) {
    return (
      <div className="group flex items-start gap-1">
        <div className="min-w-0 flex-1">{display}</div>
        {!disabled && (
          <Button
            type="text"
            size="small"
            aria-label={`修改${label}`}
            className="opacity-0 group-hover:opacity-100 focus:opacity-100"
            icon={<Pencil size={13} />}
            onClick={start}
          />
        )}
      </div>
    );
  }

  const editor = {
    enum: (
      <Select
        autoFocus
        size="small"
        className="min-w-40"
        aria-label={label}
        value={draft as string}
        options={Object.entries(ENUMS[path] ?? {}).map(([v, l]) => ({ value: v, label: l }))}
        onChange={setDraft}
        onKeyDown={keys}
      />
    ),
    boolean: <Switch autoFocus size="small" aria-label={label} checked={!!draft} onChange={setDraft} />,
    number: <InputNumber autoFocus size="small" aria-label={label} value={draft as number} onChange={setDraft} onKeyDown={keys} />,
    long: (
      <Input.TextArea
        autoFocus
        aria-label={label}
        className={path === "description" ? "" : "font-mono"}
        autoSize={{ minRows: 2, maxRows: 8 }}
        value={(draft as string) ?? ""}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={keys}
      />
    ),
    text: <Input autoFocus size="small" aria-label={label} value={(draft as string) ?? ""} onChange={(e) => setDraft(e.target.value)} onKeyDown={keys} />,
    json: (
      <Input.TextArea
        autoFocus
        aria-label={label}
        className="font-mono text-xs"
        autoSize={{ minRows: 3, maxRows: 12 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={keys}
      />
    ),
  }[kind];

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-1">
        <div className="min-w-0 flex-1">{editor}</div>
        <Button type="text" size="small" aria-label={`保存${label}`} loading={saving} icon={<Check size={13} />} onClick={() => void save()} />
        <Button type="text" size="small" aria-label={`取消修改${label}`} disabled={saving} icon={<X size={13} />} onClick={cancel} />
      </div>
      {error && <Alert type="error" showIcon message={error} />}
    </div>
  );
}
