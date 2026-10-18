import {
  Box,
  Database,
  GitBranch,
  Network,
  Search,
  Settings,
  Rocket,
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

const SEARCH_ICONS = { object_type: Box, link_type: GitBranch, metric: Sigma, dataset: Database };
const SEARCH_PAGES = { object_type: "objects", link_type: "relations", metric: "view", dataset: "mappings" };

// 本体管理 / 数据管理 / 空间设置。本体管理按“看 → 建 → 发布”排列；
// 数据管理里先接数据源再做映射，跟着实际操作顺序走。
const navigation = [
  {
    group: "本体管理",
    items: [
      { to: "view", label: "本体视图", icon: Network },
      { to: "objects", label: "本体对象", icon: Box },
      { to: "relations", label: "本体关系", icon: GitBranch },
      { to: "builder", label: "本体构建", icon: Sparkles },
      { to: "delivery", label: "本体发布", icon: Rocket },
    ],
  },
  {
    group: "数据管理",
    items: [
      { to: "connections", label: "数据连接", icon: Plug },
      { to: "mappings", label: "数据映射", icon: Database },
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
    <div
      className={`grid h-dvh w-full grid-rows-[52px_minmax(0,1fr)] overflow-hidden bg-surface max-[1100px]:h-[calc(100dvh/var(--app-scale))] max-[1100px]:w-[1100px] max-[1100px]:[zoom:var(--app-scale)] ${collapsed ? "grid-cols-[56px_minmax(0,1fr)]" : "grid-cols-[clamp(184px,14.4vw,208px)_minmax(0,1fr)] max-[1100px]:grid-cols-[184px_minmax(0,1fr)]"}`}
    >
      <header className="z-[5] col-span-full flex items-center justify-between border-b border-rule-soft bg-surface px-5">
        <Link to="/" className="flex items-center gap-5 text-inherit">
          <Brand />
        </Link>
        <div className="flex items-center gap-5 text-xs">
          <Tooltip title="搜索本体 ⌘K">
            <Button type="text" aria-label="搜索本体" icon={<Search size={17} />} onClick={openSearch} />
          </Tooltip>
          <Link to="/" className="flex items-center gap-2 text-inherit">
            <Globe size={16} className="text-accent" />
            {workspace.name}
            <ChevronDown size={13} />
          </Link>
          <span className="flex items-center gap-2">
            <Avatar size={24} className="!bg-accent !text-[11px]">
              {user.display_name.slice(0, 1).toUpperCase() || "A"}
            </Avatar>
            {user.display_name}
          </span>
        </div>
      </header>
      <aside className={`flex min-h-0 flex-col border-r border-rule-soft bg-surface pt-5 pb-3 ${collapsed ? "px-1.5" : "px-3"}`}>
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
                {heading && !collapsed && <h2 className="m-0 px-3.5 pb-1 text-xs font-medium text-muted">{group}</h2>}
                {visible.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={`/workspaces/${workspaceId}/${to}`}
                    title={collapsed ? label : undefined}
                    className={({ isActive }) =>
                      `flex min-h-10 items-center gap-3 rounded-[22px] px-3.5 text-[13px] ${isActive ? "bg-accent-soft font-semibold !text-accent" : "!text-ink-2 hover:bg-surface-soft"} ${collapsed ? "px-3" : ""}`
                    }
                  >
                    <Icon size={17} className="flex-none" />
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
            className="!text-xs !text-muted"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "展开导航" : "收起导航"}
            icon={collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          >
            {!collapsed && "收起导航"}
          </Button>
        </div>
      </aside>
      <main className="min-h-0 min-w-0 overflow-hidden" key={workspaceId}>
        <WorkspaceContextProvider.Provider value={{ workspace, user, refresh: load }}>
          <WorkspaceTabs key={`${user.id}:${workspaceId}`} workspaceId={workspaceId} userId={user.id} />
        </WorkspaceContextProvider.Provider>
      </main>
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
          prefix={<Search size={15} />}
          aria-label="搜索关键词"
          placeholder="名称、技术名、描述或同义词"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="mt-3 flex max-h-[420px] flex-col overflow-auto">
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
                  className="!flex !h-auto !justify-start !gap-2 !py-2 text-left"
                  onClick={() => {
                    setSearching(false);
                    navigate(
                      `/workspaces/${workspaceId}/${SEARCH_PAGES[r.kind]}?inspect=${r.kind}:${r.definition.id}`,
                    );
                  }}
                >
                  <Icon size={16} />
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
    </div>
  );
}
