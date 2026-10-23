import { definitionReads } from "../api/definitionReads";
import {
  Box,
  Database,
  Network,
  Search,
  Settings,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronDown,
  Globe,
  Plug,
} from "lucide-react";
import {
  NavLink,
  useParams,
  Link,
  useLocation,
  Navigate,
} from "react-router-dom";
import { Avatar, Button, Tooltip } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { WorkspaceContextProvider } from "../hooks/useWorkspaceContext";
import { OntologySearchDialog } from "./OntologySearchDialog";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { Brand } from "./Brand";
import { ErrorSurface, LoadingSurface } from "./AsyncState";
import { ApplicationFrame } from "./layout";

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
  const [searching, setSearching] = useState(false);
  const load = useCallback(() => {
    setError("");
    Promise.all([api.workspace(workspaceId), api.me()])
      .then(([w, u]) => {
        definitionReads.authorize(u.id, w.id, [w.role, w.visibility].join(":"));
        setWorkspace(w);
        setUser(u);
      })
      .catch((e: Error) => setError(e.message));
  }, [workspaceId]);
  useEffect(load, [load]);
  useEffect(() => {
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);
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
  const openSearch = useCallback(() => setSearching(true), []);
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
      <OntologySearchDialog workspaceId={workspaceId} open={searching} onClose={() => setSearching(false)} />
    </ApplicationFrame>
  );
}
