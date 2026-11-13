import { definitionReads } from "../api/definitionReads";
import {
  Box,
  Database,
  Info,
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
import { Button, Tooltip } from "antd";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { WorkspaceContextProvider } from "../hooks/useWorkspaceContext";
import { getWorkspacePermissions } from "../hooks/useWorkspacePermissions";
import { OntologySearchDialog } from "./OntologySearchDialog";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { Brand } from "./Brand";
import { ErrorSurface, LoadingSurface } from "./AsyncState";
import { NoAccessResult } from "./NoAccessResult";
import { PlatformFrame } from "./PlatformFrame";
import { UserMenu } from "./UserMenu";
import { ApplicationFrame, DirectoryFrame } from "./layout";

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

export function AppShell() {
  const { workspaceId = "" } = useParams();
  const location = useLocation();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [accessDenied, setAccessDenied] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [searching, setSearching] = useState(false);
  const load = useCallback(() => {
    setError("");
    setAccessDenied(false);
    void Promise.allSettled([api.workspace(workspaceId), api.me()]).then(
      ([wsResult, meResult]) => {
        if (meResult.status === "fulfilled") setUser(meResult.value);
        if (wsResult.status === "rejected") {
          const reason = wsResult.reason;
          if (reason instanceof ApiError && (reason.status === 403 || reason.status === 404)) {
            setAccessDenied(true);
            return;
          }
          setError(reason instanceof Error ? reason.message : "加载工作空间失败");
          return;
        }
        if (meResult.status === "rejected") {
          const reason = meResult.reason;
          setError(reason instanceof Error ? reason.message : "加载用户信息失败");
          return;
        }
        const w = wsResult.value;
        const u = meResult.value;
        definitionReads.authorize(
          u.id,
          w.id,
          [w.role, w.visibility, w.is_public, u.is_platform_admin].join(":"),
        );
        setWorkspace(w);
      },
    );
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
  if (accessDenied) {
    const content = <NoAccessResult subtitle="该工作空间不存在，或你不是该私有空间的成员。" />;
    if (user) return <PlatformFrame user={user}>{content}</PlatformFrame>;
    return (
      <DirectoryFrame header={<Link to="/"><Brand /></Link>}>
        {content}
      </DirectoryFrame>
    );
  }
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (location.pathname.replace(/\/$/, "") === `/workspaces/${workspaceId}`)
    return <Navigate to={`/workspaces/${workspaceId}/view`} replace />;
  if (!workspace || workspace.id !== workspaceId || !user)
    return <LoadingSurface label="正在读取工作空间…" />;
  const permissions = getWorkspacePermissions(workspace, user);
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
            <UserMenu user={user} />
          </div>
        </>
      }
      sidebar={
        <>
          <nav aria-label="工作空间导航" className="flex flex-col gap-4">
            {navigation.map(({ group, items }) => {
              const visible = items.filter((n) =>
                n.to === "settings" ? permissions.canManage : true,
              );
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
        <div className="flex h-full min-h-0 flex-col">
          {permissions.readOnlyBanner && (
            <div
              role="status"
              className="flex shrink-0 items-center gap-2 border-b border-rule bg-accent-soft px-5 py-2 text-xs text-ink-2"
            >
              <Info size={14} className="shrink-0 text-accent" aria-hidden="true" />
              <span>{permissions.readOnlyBanner}</span>
            </div>
          )}
          <div className="flex min-h-0 flex-1 flex-col">
            <WorkspaceTabs key={`${user.id}:${workspaceId}`} workspaceId={workspaceId} userId={user.id} />
          </div>
        </div>
      </WorkspaceContextProvider.Provider>
      <OntologySearchDialog workspaceId={workspaceId} open={searching} onClose={() => setSearching(false)} />
    </ApplicationFrame>
  );
}
