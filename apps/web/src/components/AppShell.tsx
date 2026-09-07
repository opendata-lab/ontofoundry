import {
  Box,
  Database,
  GitBranch,
  Network,
  Search,
  Settings,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
  Globe,
} from "lucide-react";
import {
  NavLink,
  useParams,
  Link,
  useNavigate,
  useLocation,
  Navigate,
} from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { OntologyType, User, Workspace } from "../api/types";
import { WorkspaceContextProvider } from "../hooks/useWorkspaceContext";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { Brand } from "./Brand";
import { ErrorSurface, LoadingSurface } from "./AsyncState";

// 发布与服务不再占一级导航：发布是本体视图、对象目录和建模工作台上的操作，
// 版本与服务说明作为它的二级页面打开。
const navigation = [
  { to: "view", label: "本体视图", icon: Network },
  { to: "objects", label: "业务对象", icon: Box },
  { to: "relations", label: "本体关系", icon: GitBranch },
  { to: "mappings", label: "数据映射", icon: Database },
  { to: "builder", label: "本体自动构建", icon: Sparkles },
  { to: "settings", label: "空间设置", icon: Settings },
];
export function AppShell() {
  const { workspaceId = "" } = useParams();
  const location = useLocation();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<OntologyType[]>([]);
  const dialog = useRef<HTMLDialogElement>(null);
  const navigate = useNavigate();
  const load = useCallback(() => {
    setError("");
    Promise.all([api.workspace(workspaceId), api.me()])
      .then(([w, u]) => {
        setWorkspace(w);
        setUser(u);
      })
      .catch((e: Error) => setError(e.message));
  }, [workspaceId]);
  useEffect(load, [load]);
  useEffect(() => {
    const fit = () =>
      document.documentElement.style.setProperty(
        "--app-scale",
        String(Math.min(1, window.innerWidth / 1100)),
      );
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  const openSearch = useCallback(() => {
    setQuery("");
    setResults([]);
    dialog.current?.showModal();
    api
      .types(workspaceId)
      .then((r) => setResults(r.items))
      .catch(() => setResults([]));
  }, [workspaceId]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        openSearch();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [openSearch]);
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (location.pathname.replace(/\/$/, "") === `/workspaces/${workspaceId}`)
    return <Navigate to={`/workspaces/${workspaceId}/view`} replace />;
  if (!workspace || workspace.id !== workspaceId || !user)
    return <LoadingSurface label="正在读取工作空间…" />;
  return (
    <div className={"ref-shell" + (collapsed ? " is-collapsed" : "")}>
      <header className="ref-topbar">
        <Link to="/" className="ref-brand">
          <Brand />
          <span>本体管理</span>
        </Link>
        <div className="ref-topbar-actions">
          <button
            className="icon-button"
            aria-label="搜索本体"
            title="搜索本体 ⌘K"
            onClick={openSearch}
          >
            <Search size={17} />
          </button>
          <Link to="/" className="workspace-label">
            <Globe size={16} />
            {workspace.name}
            <ChevronDown size={13} />
          </Link>
          <span className="account-label">
            <span className="avatar avatar--small">A</span>
            {user.display_name}
          </span>
        </div>
      </header>
      <aside className="ref-sidebar">
        <nav aria-label="工作空间导航">
          {navigation
            .filter(
              (n) =>
                workspace.role ||
                ["view", "objects", "relations"].includes(n.to),
            )
            .map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={`/workspaces/${workspaceId}/${to}`}
                title={collapsed ? label : undefined}
              >
                <Icon size={17} />
                <span>{label}</span>
              </NavLink>
            ))}
        </nav>
        <button
          className="collapse-nav"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? "展开导航" : "收起导航"}
        >
          {collapsed ? (
            <PanelLeftOpen size={17} />
          ) : (
            <PanelLeftClose size={17} />
          )}
          <span>收起导航</span>
        </button>
      </aside>
      <main className="ref-page" key={workspaceId}>
        <WorkspaceContextProvider.Provider
          value={{ workspace, user, refresh: load }}
        >
          <WorkspaceTabs
            key={`${user.id}:${workspaceId}`}
            workspaceId={workspaceId}
            userId={user.id}
          />
        </WorkspaceContextProvider.Provider>
      </main>
      <dialog
        ref={dialog}
        className="ref-dialog search-dialog"
        aria-label="搜索本体"
      >
        <header>
          <h2>搜索已发布本体</h2>
          <button
            className="icon-button"
            onClick={() => dialog.current?.close()}
            aria-label="关闭搜索"
          >
            ×
          </button>
        </header>
        <label className="ref-search">
          <Search size={16} />
          <input
            autoFocus
            aria-label="搜索关键词"
            placeholder="名称、API 标识或描述"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="search-results">
          {results
            .filter((r) =>
              (r.name + r.technical_name + r.description)
                .toLowerCase()
                .includes(query.toLowerCase()),
            )
            .map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  dialog.current?.close();
                  navigate(
                    "/workspaces/" +
                      workspaceId +
                      "/" +
                      (r.kind === "object_type"
                        ? "objects/" + r.id
                        : "relations/" + r.id),
                  );
                }}
              >
                <Box size={16} />
                {r.name}
                <small>{r.technical_name}</small>
              </button>
            ))}
        </div>
        {!results.length && <p className="muted">暂无已发布本体</p>}
      </dialog>
    </div>
  );
}
