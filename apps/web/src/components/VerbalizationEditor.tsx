import { Plus, RotateCcw, Trash2 } from "lucide-react";

// Ossie requires a reading for every relationship. The platform generates a
// standard one from the business names, so an empty list is not missing data —
// it means "use the generated reading". Writing one here replaces it.
export function VerbalizationEditor({
  label,
  concepts,
  value,
  onChange,
}: {
  label: string;
  concepts: string[];
  value: string[] | undefined;
  onChange: (next: string[]) => void;
}) {
  const lines = value ?? [];
  return (
    <div className="verbalization-editor">
      <div className="mapping-heading">
        <h3>{label}</h3>
        {lines.length > 0 && (
          <button
            type="button"
            className="button button--text"
            onClick={() => onChange([])}
          >
            <RotateCcw size={13} />
            恢复默认
          </button>
        )}
      </div>
      {lines.length === 0 ? (
        <>
          <p className="muted">
            未自定义，发布时按业务名称生成标准读法。自定义后按你写的原文导出。
          </p>
          <button
            type="button"
            className="button button--secondary"
            onClick={() => onChange([""])}
          >
            <Plus size={14} />
            自定义读法
          </button>
        </>
      ) : (
        <>
          {lines.map((line, index) => (
            <div className="verbalization-line" key={index}>
              <input
                aria-label={label + " " + (index + 1)}
                value={line}
                placeholder={
                  concepts.length > 1
                    ? `{${concepts[0]}}…{${concepts[1]}}`
                    : `{${concepts[0] ?? "概念"}}…`
                }
                onChange={(e) =>
                  onChange(
                    lines.map((item, position) =>
                      position === index ? e.target.value : item,
                    ),
                  )
                }
              />
              <button
                type="button"
                className="icon-button"
                aria-label={"删除" + label + " " + (index + 1)}
                onClick={() =>
                  onChange(lines.filter((_, position) => position !== index))
                }
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button button--text"
            onClick={() => onChange([...lines, ""])}
          >
            <Plus size={13} />
            添加一句
          </button>
          <p className="muted">
            {"用 " +
              concepts.map((name) => `{${name}}`).join("、") +
              " 引用这条关系里的概念，其余是自由文本。发布时按 Apache Ossie 规则校验这些占位符。"}
          </p>
        </>
      )}
    </div>
  );
}
