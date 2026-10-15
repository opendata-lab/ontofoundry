import { isObject, type PanelProps } from "../../lib/elementModel";

/** Actions use the same compact table density as properties and rules. */
export function ActionsPanel({ draft, type, editing, change }: PanelProps) {
  const actions = draft.actions.filter((a) =>
    isObject(type)
      ? a.input_type_id === type.id
      : a.effects.some((e) => e.link_type_id === type.id),
  );
  const updateName = (id: string, name: string) =>
    change({
      ...draft,
      actions: draft.actions.map((a) => (a.id === id ? { ...a, name } : a)),
    });
  return (
    <div className="om-table-wrap">
      <table className="om-table om-actions">
        <thead>
          <tr>
            <th>名称</th>
            <th>参数</th>
            <th>影响</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((action) => (
            <tr key={action.id} data-element-id={action.id}>
              <td>
                {editing ? (
                  <input
                    required
                    aria-label="动作名称"
                    value={action.name}
                    onChange={(e) => updateName(action.id, e.target.value)}
                  />
                ) : (
                  action.name
                )}
              </td>
              <td>
                {action.parameters.map((p) => (
                  <code key={p.id} className="om-action-line">
                    {p.name}
                    {p.required ? " *" : ""}
                  </code>
                ))}
              </td>
              <td>
                {action.effects.map((effect) => (
                  <span key={effect.id} className="om-action-line">
                    {
                      {
                        set_property: "设置属性",
                        create_link: "创建关系",
                        delete_link: "删除关系",
                      }[effect.kind]
                    }{" "}
                    ·{" "}
                    {draft.properties.find((p) => p.id === effect.property_id)
                      ?.name ??
                      draft.link_types.find((l) => l.id === effect.link_type_id)
                        ?.name}
                    {effect.expression && (
                      <code className="om-sub">{effect.expression}</code>
                    )}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
