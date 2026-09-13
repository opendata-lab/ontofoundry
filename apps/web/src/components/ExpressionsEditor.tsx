import { Plus, Trash2 } from "lucide-react";

export function ExpressionsEditor({
  value,
  onChange,
  label = "规则与约束",
  onlyConstraints = false,
  disabled = false,
}: {
  value: { requires?: string[]; derived_by?: string[] };
  onChange: (next: { requires?: string[]; derived_by?: string[] }) => void;
  label?: string;
  onlyConstraints?: boolean;
  disabled?: boolean;
}) {
  return (
    <details className="expression-editor">
      <summary>{label}</summary>
      <p className="muted">表达式随本体校验和发布保存，当前不执行推理。</p>
      {(["requires", "derived_by"] as const)
        .filter((kind) => !onlyConstraints || kind === "requires")
        .map((kind) => (
          <section key={kind}>
            <div className="mapping-heading">
              <h3>
                {kind === "requires" ? "约束" : "派生规则"}{" "}
                <small>{kind}</small>
              </h3>
              <button
                type="button"
                className="button button--text"
                disabled={disabled || (value[kind]?.length ?? 0) >= 20}
                onClick={() =>
                  onChange({ [kind]: [...(value[kind] ?? []), ""] })
                }
              >
                <Plus size={13} />
                添加
              </button>
            </div>
            {(value[kind] ?? []).map((expression, index) => (
              <div className="verbalization-line" key={index}>
                <textarea
                  disabled={disabled}
                  aria-label={`${label} ${kind} ${index + 1}`}
                  maxLength={480}
                  rows={2}
                  value={expression}
                  onChange={(e) =>
                    onChange({
                      [kind]: value[kind]!.map((line, i) =>
                        i === index ? e.target.value : line,
                      ),
                    })
                  }
                />
                <button
                  type="button"
                  disabled={disabled}
                  className="icon-button"
                  aria-label={`删除 ${kind} ${index + 1}`}
                  onClick={() =>
                    onChange({
                      [kind]: value[kind]!.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </section>
        ))}
    </details>
  );
}
