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
  Plug,
  Sigma,
} from "lucide-react";
import {
  NavLink,
  useParams,
  Link,
  useNavigate,
  useLocation,
  Navigate,
} from "react-router-dom";
import { Avatar, Button, Empty, Input, Modal, Tooltip } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { ResourceRead, User, Workspace } from "../api/types";
import { WorkspaceContextProvider } from "../hooks/useWorkspaceContext";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { Brand } from "./Brand";
import { ErrorSurface, LoadingSurface } from "./AsyncState";
import { ApplicationFrame } from "./layout";

const SEARCH_ICONS = { object_type: Box, link_type: GitBranch, metric: Sigma, dataset: Database };
const SEARCH_PAGES = { object_type: "objects", link_type: "objects", metric: "objects", dataset: "mappings" };

// Follow the workflow: inspect, build and publish; connect data before mapping.
const navigation = [
  {
    group: "本体管理",
    items: [
      { to: "view", label: "本体视图", icon: Network },
      { to: "objects", label: "本体对象", icon: Box },
      { to: "builder", label: "本体构建", icon: Sparkles },
    ],
  },
  {
    group: "数据管理",
    items: [
      { to: "connections", label: "数据连接", icon: Plug },
      { to: "mappings", label: "数据管理", icon: Database },
    ],
  },
  { group: "空间设置", items: [{ to: "settings", label: "空间设置", icon: Settings }] },
];
/** What a reader without a workspace role may open: the published ontology,
 * and the release page, whose history and service tabs need no role. */
const READER_PAGES = ["view", "objects", "relations", "delivery"];
export function AppShell() {
  const { workspaceId = "" } = useParams();
  const location = useLocation();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ResourceRead[]>([]);
  const [searching, setSearching] = useState(false);
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
    const minimumWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--app-min-width"));
    if (!minimumWidth) return;
    const fit = () =>
      document.documentElement.style.setProperty(
        "--app-scale",
        String(Math.min(1, window.innerWidth / minimumWidth)),
      );
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  const openSearch = useCallback(() => {
    setQuery("");
    setResults([]);
    setSearching(true);
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
    <ApplicationFrame
      collapsed={collapsed}
      header={
        <>
          <Link to="/" className="flex items-center gap-5 text-inherit">
            <Brand />
          </Link>
          <div className="flex items-center gap-5 text-xs">
            <Tooltip title="搜索本体 ⌘K">
              <Button type="text" aria-label="搜索本体" icon={<Search className="size-icon" />} onClick={openSearch} />
            </Tooltip>
            <Link to="/" className="flex items-center gap-2 text-inherit">
              <Globe className="size-icon text-accent" />
              {workspace.name}
              <ChevronDown className="size-icon" />
            </Link>
            <span className="flex items-center gap-2">
              <Avatar className="size-6 bg-accent text-xs leading-6 text-accent-ink">
                {user.display_name.slice(0, 1).toUpperCase() || "A"}
              </Avatar>
              {user.display_name}
            </span>
          </div>
        </>
      }
      sidebar={
        <>
          <nav aria-label="工作空间导航" className="flex flex-col gap-4">
            {navigation.map(({ group, items }) => {
              const visible = items.filter((n) => workspace.role || READER_PAGES.includes(n.to));
              if (!visible.length) return null;
              // A group of one item needs no heading: the item names itself.
              const heading = visible.length > 1 || visible[0].label !== group;
              return (
                <div
                  className="flex flex-col gap-1 [&+&]:border-t [&+&]:border-rule-soft [&+&]:pt-3"
                  key={group}
                  role="group"
                  aria-label={group}
                >
                  {heading && !collapsed && <h2 className="m-0 px-3 pb-1 text-xs font-medium text-muted">{group}</h2>}
                  {visible.map(({ to, label, icon: Icon }) => (
                    <NavLink
                      key={to}
                      to={`/workspaces/${workspaceId}/${to}`}
                      title={collapsed ? label : undefined}
                      className={({ isActive }) =>
                        `app-nav-link flex min-h-10 items-center gap-3 rounded-sm px-3 text-sm ${isActive ? "bg-accent-soft font-semibold text-accent hover:text-accent" : "text-ink-2 hover:bg-surface-soft hover:text-ink"}`
                      }
                    >
                      <Icon className="size-icon flex-none" />
                      {!collapsed && <span>{label}</span>}
                    </NavLink>
                  ))}
                </div>
              );
            })}
          </nav>
          <div className="mt-auto flex justify-center border-t border-rule-soft pt-3">
            <Button
              type="text"
              size="small"
              className="text-xs text-muted"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "展开导航" : "收起导航"}
              icon={collapsed ? <PanelLeftOpen className="size-icon" /> : <PanelLeftClose className="size-icon" />}
            >
              {!collapsed && "收起导航"}
            </Button>
          </div>
        </>
      }
    >
      <WorkspaceContextProvider.Provider value={{ workspace, user, refresh: load }}>
        <WorkspaceTabs key={`${user.id}:${workspaceId}`} workspaceId={workspaceId} userId={user.id} />
      </WorkspaceContextProvider.Provider>
      <Modal
        open={searching}
        onCancel={() => setSearching(false)}
        title="搜索已发布本体"
        footer={null}
        destroyOnHidden
      >
        <Input
          autoFocus
          allowClear
          prefix={<Search className="size-icon" />}
          aria-label="搜索关键词"
          placeholder="名称、技术名、描述或同义词"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="mt-3 flex max-h-app-search flex-col overflow-auto">
          {results
            .filter((r) => {
              const d = r.definition as { name: string; technical_name?: string; description?: string; synonyms?: string[] };
              return [d.name, d.technical_name ?? "", d.description ?? "", ...(d.synonyms ?? [])]
                .join(" ")
                .toLowerCase()
                .includes(query.toLowerCase());
            })
            .map((r) => {
              const Icon = SEARCH_ICONS[r.kind];
              return (
                <Button
                  key={r.kind + r.definition.id}
                  type="text"
                  className="h-auto justify-start gap-2 py-2 text-left whitespace-normal"
                  onClick={() => {
                    setSearching(false);
                    navigate(
                      `/workspaces/${workspaceId}/${SEARCH_PAGES[r.kind]}?${r.kind === "link_type" ? "catalogTab=relations&" : r.kind === "metric" ? "catalogTab=metrics&" : ""}inspect=${r.kind}:${r.definition.id}`,
                    );
                  }}
                >
                  <Icon className="size-icon" />
                  <span>{r.definition.name}</span>
                  <code className="text-xs text-muted">
                    {"technical_name" in r.definition ? r.definition.technical_name : ""}
                  </code>
                </Button>
              );
            })}
          {!results.length && <Empty description="暂无已发布本体" />}
        </div>
      </Modal>
    </ApplicationFrame>
  );
}
