import { useCallback, useEffect, useState } from "react";
import { workspaceRequest, modelingApi } from "../api/client";
import type { Capabilities, DataAgentHealth } from "../api/types";
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
  const [dataagentHealth, setDataagentHealth] =
    useState<DataAgentHealth | null>(null);
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
    workspaceRequest<DataAgentHealth>(
      workspace.id,
      "/settings/dataagent-health",
    )
      .then(setDataagentHealth)
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
        {/* 这里只留用户用得上的两条：问数能不能用，材料该传成什么样。
            原本还列了「协议」和「内置方法」：协议是写死的字面量，后端支持两种
            api_format 之后它可能是错的，而 ontofoundry 本就不知道管理员配了哪种；
            「内置方法」是 skill 目录名，属内部实现。模型那行的值是固定的运行时名
            而非模型名，标签却写「内网大模型」——三条都不可操作，也无法自证。 */}
        <section className="detail-section">
          <h2>智能问数</h2>
          <dl className="ref-definition">
            <div>
              <dt>状态</dt>
              <dd>{cap?.agent_configured ? "可用" : "尚未配置"}</dd>
            </div>
            <div>
              <dt>材料格式</dt>
              <dd>Markdown · 最大 {cap?.max_file_mb ?? 256} MB</dd>
            </div>
          </dl>
          <p className="muted">模型接口由服务器环境配置。</p>
        </section>
        <section className="detail-section">
          <h2>DataAgent 连通性</h2>
          <p className="muted">
            只读检查。地址、站点与凭据均由部署环境和 DataAgent 管理端配置。
          </p>
          {dataagentHealth ? (
            <table className="ref-table dataagent-health-table">
              <thead>
                <tr>
                  <th>检查项</th>
                  <th>状态</th>
                  <th>结果与修复指引</th>
                </tr>
              </thead>
              <tbody>
                {dataagentHealth.checks.map((check) => (
                  <tr key={check.name}>
                    <td>{check.name}</td>
                    <td>
                      <span
                        className={
                          "status-chip " +
                          (check.ok
                            ? "status-chip--published"
                            : "dataagent-health-status--failed")
                        }
                      >
                        {check.ok ? "通过" : "需处理"}
                      </span>
                    </td>
                    <td>
                      <div>{check.message}</div>
                      {check.hint && <div className="muted">{check.hint}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">正在检查…</p>
          )}
        </section>
      </div>
    </div>
  );
}
