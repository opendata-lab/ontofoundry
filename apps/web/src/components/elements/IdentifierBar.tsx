import { KeyRound } from "lucide-react";
import { useState } from "react";
import { isObject, type PanelProps } from "../../lib/elementModel";
import { objectMapping } from "../../lib/objectMapping";
import {
  chooseIdentifier,
  propertyReadonly,
} from "../../lib/objectMappingEditing";
import { InspectorDialog } from "./InspectorDialog";
import { ReadonlyIcon } from "./MappingWidgets";

export function IdentifierBar(props: PanelProps & { heading?: boolean }) {
  const { draft, type, nativeDraft, editing, heading = true } = props;
  const [opened, setOpened] = useState(false);
  const [selected, setSelected] = useState("");
  if (!isObject(type)) return null;
  const record = objectMapping(draft, type, nativeDraft);
  const reason =
    record.keys.length > 1
      ? "当前标识包含多列，单属性保存不能保留复合标识；请在「数据映射 › 语义模型 › 概念映射」中编辑复合实例标识。"
      : type.extends.length &&
          !draft.properties.some(
            (p) => p.owner_type_id === type.id && p.identifier,
          )
        ? "实例标识继承自父对象，请编辑父对象。"
        : null;
  const identifier =
    record.keys
      .filter((e) => e.expression)
      .map((e) => e.expression)
      .join(" + ") ||
    record.properties
      .filter((p) => p.property.identifier)
      .map((p) => p.property.technical_name)
      .join(" + ");
  const candidates = record.properties.filter(
    (p) =>
      !p.inherited &&
      !propertyReadonly(props, p.property) &&
      p.entries.some((e) => e.expression && !e.pending),
  );
  return (
    <>
      <div className="om-identifier-bar">
        {heading && <span>实例标识</span>}
        <KeyRound size={16} />
        {identifier ? (
          <code>{identifier}</code>
        ) : (
          <span className="muted">未设置</span>
        )}
        {editing && (
          <div className="om-push om-inline">
            <button
              type="button"
              className="element-text-button"
              disabled={!!reason || !candidates.length}
              onClick={() => {
                setSelected(
                  candidates.find((p) => p.property.identifier)?.property.id ??
                    "",
                );
                setOpened(true);
              }}
            >
              设置实例标识
            </button>
            <ReadonlyIcon
              reason={
                reason ??
                (!candidates.length
                  ? "请先绑定本对象的属性来源字段，再设置实例标识。"
                  : null)
              }
            />
          </div>
        )}
      </div>
      {opened && (
        <InspectorDialog
          title="设置实例标识"
          onClose={() => setOpened(false)}
          footer={
            <>
              <button
                type="button"
                className="button button--secondary om-push"
                onClick={() => setOpened(false)}
              >
                取消
              </button>
              <button
                type="button"
                className="button button--primary"
                disabled={!selected}
                onClick={() => {
                  const property = candidates.find(
                    (p) => p.property.id === selected,
                  )?.property;
                  if (property) chooseIdentifier(props, property);
                  setOpened(false);
                }}
              >
                保存
              </button>
            </>
          }
        >
          <div className="om-key-picker">
            {candidates.map(({ property }) => (
              <label key={property.id} className="om-key-option">
                <input
                  type="radio"
                  name="instance-identifier"
                  checked={selected === property.id}
                  onChange={() => setSelected(property.id)}
                />
                <span>
                  {property.name}
                  <code className="om-sub">{property.technical_name}</code>
                </span>
              </label>
            ))}
          </div>
        </InspectorDialog>
      )}
    </>
  );
}
