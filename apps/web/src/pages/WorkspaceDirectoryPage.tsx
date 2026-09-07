import { ArrowRight, LockKeyhole, Plus } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { Brand } from "../components/Brand";

export function WorkspaceDirectoryPage() {
  const navigate = useNavigate();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");

  const load = useCallback(() => {
    setError("");
    Promise.all([api.workspaces(), api.me()])
      .then(([workspaceData, userData]) => {
        setWorkspaces(workspaceData.items);
        setUser(userData);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(load, [load]);

  const createWorkspace = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreating(true);
    setFormError("");
    const data = new FormData(event.currentTarget);
    try {
      const workspace = await api.createWorkspace({
        name: String(data.get("name") ?? ""),
        slug: String(data.get("slug") ?? ""),
        description: String(data.get("description") ?? ""),
      });
      dialogRef.current?.close();
      navigate("/workspaces/" + workspace.id + "/view");
    } catch (reason) {
      setFormError(
        reason instanceof Error ? reason.message : "工作空间创建失败",
      );
    } finally {
      setCreating(false);
    }
  };

  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!user) return <LoadingSurface label="正在读取工作空间目录…" />;

  return (
    <div className="directory">
      <header className="directory__header">
        <Brand />
        <div className="directory__user">
          <span className="avatar avatar--small">A</span>
          <span>{user.display_name}</span>
        </div>
      </header>
      <main className="directory__main">
        <div className="directory__title">
          <div>
            <h1>工作空间</h1>
            <p>每个工作空间维护一张独立本体图和一个当前发布版本。</p>
          </div>
          <button
            className="button button--primary"
            onClick={() => dialogRef.current?.showModal()}
          >
            <Plus size={17} aria-hidden="true" />
            创建工作空间
          </button>
        </div>
        {workspaces.length ? (
          <section className="workspace-list" aria-label="工作空间列表">
            {workspaces.map((workspace) => (
              <Link
                key={workspace.id}
                className="workspace-row"
                to={"/workspaces/" + workspace.id + "/view"}
              >
                <div className="workspace-row__identity">
                  <span className="workspace-row__mark">
                    {workspace.name.slice(0, 1)}
                  </span>
                  <span>
                    <strong>{workspace.name}</strong>
                    <small>{workspace.description || "尚未填写空间说明"}</small>
                  </span>
                </div>
                <div className="workspace-row__metric">
                  <strong>{workspace.object_type_count}</strong>
                  <small>业务对象</small>
                </div>
                <div className="workspace-row__metric">
                  <strong>{workspace.link_type_count}</strong>
                  <small>本体关系</small>
                </div>
                <div className="workspace-row__version">
                  {workspace.current_version ? (
                    <>
                      <span className="status-chip status-chip--published">
                        v{workspace.current_version}
                      </span>
                      <small>已发布</small>
                    </>
                  ) : (
                    <span className="status-chip">尚未发布</span>
                  )}
                </div>
                <div className="workspace-row__access">
                  {workspace.visibility === "published_only" && (
                    <LockKeyhole size={14} aria-label="仅本体可见" />
                  )}
                  <span>
                    {workspace.role === "admin"
                      ? "空间管理员"
                      : workspace.role === "member"
                        ? "空间成员"
                        : "仅本体可见"}
                  </span>
                  <ArrowRight size={17} aria-hidden="true" />
                </div>
              </Link>
            ))}
          </section>
        ) : (
          <div className="empty-state">
            <p>还没有工作空间。创建后即可导入 Markdown 并开始建模。</p>
            <button
              className="button button--primary"
              onClick={() => dialogRef.current?.showModal()}
            >
              创建工作空间
            </button>
          </div>
        )}
      </main>

      <dialog ref={dialogRef} className="form-dialog">
        <form onSubmit={createWorkspace}>
          <div className="form-dialog__header">
            <div>
              <h2>创建工作空间</h2>
              <p>空间名称在平台内不能重复。</p>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="关闭"
              onClick={() => dialogRef.current?.close()}
            >
              ×
            </button>
          </div>
          <label>
            空间名称
            <input name="name" required maxLength={120} autoFocus />
          </label>
          <label>
            空间标识
            <input
              name="slug"
              required
              pattern="[a-z][a-z0-9-]*"
              placeholder="manufacturing-domain"
            />
            <small>
              用于 API 与 Ossie ontology name，只能使用小写字母、数字和连字符。
            </small>
          </label>
          <label>
            空间说明
            <textarea name="description" maxLength={1200} rows={3} />
          </label>
          <div className="form-helper" aria-live="polite">
            {formError}
          </div>
          <div className="form-dialog__actions">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => dialogRef.current?.close()}
            >
              取消
            </button>
            <button
              className="button button--primary"
              type="submit"
              disabled={creating}
            >
              {creating ? "正在创建…" : "创建工作空间"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
