import { useCallback, useEffect, useState } from "react";
import { workspaceRequest, modelingApi } from "../api/client";
import type { Capabilities } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { usePageTab } from "../hooks/usePageTab";

export function SettingsPage() {
  const { workspace, user, refresh } = useWorkspaceContext();
  const [members, setMembers] = useState<
    {
      id: number;
      user_id: string;
      name: string;
      subject: string;
      role: string;
    }[]
  >([]);
  const [cap, setCap] = useState<Capabilities | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [infoDirty, setInfoDirty] = useState(false);
  const [memberDirty, setMemberDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  usePageTab({ dirty: infoDirty || memberDirty, busy });
  const load = useCallback(
    () =>
      workspaceRequest<{ items: typeof members }>(
        workspace.id,
        "/members",
      ).then((r) => setMembers(r.items)),
    [workspace.id],
  );
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    modelingApi
      .capabilities(workspace.id)
      .then(setCap)
      .catch((e: Error) => setError(e.message));
  }, [workspace.id, load]);
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>空间设置</h1>
      </header>
      <div className="management-content settings-content">
        {error && <p className="inline-error">{error}</p>}
        <section className="detail-section">
          <h2>空间信息</h2>
          <form
            onChange={() => setInfoDirty(true)}
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              setBusy(true);
              workspaceRequest(
                workspace.id,
                "",
                { name: f.get("name"), description: f.get("description") },
                "PATCH",
              )
                .then(() => {
                  refresh();
                  setNotice("空间信息已保存");
                  setInfoDirty(false);
                })
                .catch((e: Error) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            <label className="section-field">
              <span>空间名称</span>
              <input
                name="name"
                defaultValue={workspace.name}
                required
                disabled={workspace.role !== "admin"}
              />
            </label>
            <label className="section-field">
              <span>说明</span>
              <textarea
                name="description"
                rows={3}
                defaultValue={workspace.description}
                disabled={workspace.role !== "admin"}
              />
            </label>
            {workspace.role === "admin" && (
              <button className="button button--primary">保存空间信息</button>
            )}
            {notice && <span className="muted">{notice}</span>}
          </form>
        </section>
        <section className="detail-section">
          <h2>空间成员</h2>
          <p className="muted">
            非成员可查看已发布本体；材料、草稿、映射和实例仅成员可见。
          </p>
          <table className="ref-table">
            <thead>
              <tr>
                <th>用户</th>
                <th>身份标识</th>
                <th>角色</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>{m.subject}</td>
                  <td>{m.role === "admin" ? "admin" : "成员"}</td>
                  <td>
                    {workspace.role === "admin" && m.user_id !== user.id && (
                      <button
                        className="button button--text"
                        onClick={() =>
                          workspaceRequest(
                            workspace.id,
                            "/members/" + m.id,
                            undefined,
                            "DELETE",
                          )
                            .then(load)
                            .catch((e: Error) => setError(e.message))
                        }
                      >
                        移除
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {workspace.role === "admin" && (
            <form
              className="row-actions"
              onChange={() => setMemberDirty(true)}
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                const form = e.currentTarget;
                setBusy(true);
                workspaceRequest(workspace.id, "/members", {
                  subject: f.get("subject"),
                  role: f.get("role"),
                })
                  .then(() => {
                    setMemberDirty(false);
                    form.reset();
                    return load();
                  })
                  .catch((e: Error) => setError(e.message))
                  .finally(() => setBusy(false));
              }}
            >
              <input
                name="subject"
                aria-label="成员身份标识"
                placeholder="provider:sub，需先登录过平台"
                required
              />
              <select name="role" aria-label="成员角色">
                <option value="member">成员</option>
                <option value="admin">admin</option>
              </select>
              <button className="button button--secondary">添加成员</button>
            </form>
          )}
        </section>
        <section className="detail-section">
          <h2>大模型与内置方法</h2>
          <dl className="ref-definition">
            <div>
              <dt>内网大模型</dt>
              <dd>{cap?.agent_configured ? cap.model : "尚未配置"}</dd>
            </div>
            <div>
              <dt>协议</dt>
              <dd>Anthropic Messages API</dd>
            </div>
            <div>
              <dt>内置方法</dt>
              <dd>md2ossie · ontology-clarifier</dd>
            </div>
            <div>
              <dt>材料格式</dt>
              <dd>Markdown · 最大 {cap?.max_file_mb ?? 256} MB</dd>
            </div>
          </dl>
          <p className="muted">
            模型接口与连接加密主密钥由服务器环境配置，密钥不会在页面中显示。
          </p>
        </section>
      </div>
    </div>
  );
}
