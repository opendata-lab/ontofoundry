import { Alert, Button, Modal, Tabs } from "antd";
import {
  memo,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  createPath,
  NavigationType,
  parsePath,
  UNSAFE_LocationContext as LocationContext,
  useBlocker,
  useLocation,
  useNavigate,
  useNavigationType,
} from "react-router-dom";
import {
  Box,
  Database,
  GitBranch,
  Network,
  Rocket,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { PageTabContext, type PageTabMeta } from "../hooks/usePageTab";
import {
  closeTab,
  openTab,
  restoreTabs,
  tabKey,
  type PageTab,
} from "../lib/pageTabs";
import { preloadWorkspacePages } from "../lib/workspacePages";
import { LoadingSurface } from "./AsyncState";
import { WorkspaceRoutes } from "./WorkspaceRoutes";

// Each panel reads its own location, fixed to the tab's href. The router's
// context changes on every navigation; without this every open page, hidden
// or not, re-rendered on each menu switch. Ant Design renders the surrounding
// tabpanel (id, role, aria-labelledby), mounting it on first activation and
// keeping it mounted while hidden.
const TabPanel = memo(function TabPanel({
  tab,
  active,
  update,
}: {
  tab: PageTab;
  active: boolean;
  update: (id: string, meta: PageTabMeta) => void;
}) {
  const pageMeta = useRef<PageTabMeta>({});
  const elementMeta = useRef<PageTabMeta>({});
  const report = useCallback(() => update(tab.id, {
    ...pageMeta.current,
    dirty: !!pageMeta.current.dirty || !!elementMeta.current.dirty,
    busy: !!pageMeta.current.busy || !!elementMeta.current.busy,
    elementDirty: !!elementMeta.current.dirty,
    elementBusy: !!elementMeta.current.busy,
  }), [update, tab.id]);
  const setMeta = useCallback(
    (meta: PageTabMeta) => { pageMeta.current = meta; report(); },
    [report],
  );
  const setElementMeta = useCallback(
    (meta: PageTabMeta) => { elementMeta.current = meta; report(); },
    [report],
  );
  const context = useMemo(
    () => ({ active, update: setMeta, updateElement: setElementMeta }),
    [active, setMeta, setElementMeta],
  );
  const location = useMemo(
    () => ({
      location: {
        pathname: "/",
        search: "",
        hash: "",
        ...parsePath(tab.href),
        state: null,
        key: tab.id,
      },
      navigationType: NavigationType.Pop,
    }),
    [tab.href, tab.id],
  );
  return (
    <div className="h-full min-w-0 overflow-auto" inert={!active}>
      <LocationContext.Provider value={location}>
        <PageTabContext.Provider value={context}>
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <WorkspaceRoutes href={tab.href} />
          </Suspense>
        </PageTabContext.Provider>
      </LocationContext.Provider>
    </div>
  );
});

export function WorkspaceTabs({
  workspaceId,
  userId,
}: {
  workspaceId: string;
  userId: string;
}) {
  const base = `/workspaces/${workspaceId}`;
  const storageKey = `ontofoundry:page-tabs:${userId}:${workspaceId}`;
  const location = useLocation();
  const href = createPath(location);
  const navigationType = useNavigationType();
  const navigate = useNavigate();
  const [state, setState] = useState(() => {
    let raw = null;
    try {
      raw = sessionStorage.getItem(storageKey);
    } catch {
      /* Memory-only when storage is disabled. */
    }
    return openTab(restoreTabs(raw, base), href);
  });
  // Open (or bring forward) the tab for each location. This runs in a layout
  // effect with a functional update rather than during render: the router
  // renders a navigation inside a transition, and a state update made during
  // that render could be dropped when a page's synchronous title update
  // landed alongside it, leaving the previous tab on screen.
  const resyncTo = useRef<string | null>(null);
  useLayoutEffect(() => {
    setState((current) => {
      const next = openTab(current, href, navigationType === "REPLACE");
      const target = next.tabs.find((t) => t.id === next.active);
      // A bare menu link that brought an open tab forward leaves the URL short
      // of that tab's address (its session); put the address back.
      resyncTo.current = target && tabKey(target.href) !== tabKey(href) ? target.href : null;
      return next;
    });
  }, [location.key, href, navigationType]);
  useEffect(() => {
    const to = resyncTo.current;
    if (!to) return;
    resyncTo.current = null;
    void navigate(to, { replace: true });
  });
  useEffect(() => preloadWorkspacePages(), []);
  const strip = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const busy = state.tabs.some((t) => t.busy);
  const dirty = state.tabs.some((t) => t.dirty);
  const inspectionKey = (address: string) => {
    const url = new URL(address, "http://local");
    return JSON.stringify([url.pathname, url.searchParams.get("inspect"),
      url.searchParams.get("inspectSession") ?? url.searchParams.get("session"),
      url.searchParams.get("inspectSource"), url.searchParams.get("inspectPreviewHash")]);
  };
  // Pages stay mounted in their tabs, so switching within the workspace does
  // not interrupt a request running in another tab. Protect only navigation
  // that would unmount the entire workspace.
  const blocker = useBlocker(
    ({ nextLocation }) => {
      const current = state.tabs.find((t) => t.id === state.active);
      return ((busy || dirty) && !nextLocation.pathname.startsWith(base + "/")) ||
        (!!(current?.elementDirty || current?.elementBusy) &&
          inspectionKey(current.href) !== inspectionKey(createPath(nextLocation)));
    },
  );
  const blocked = blocker.state === "blocked";
  const blockingBusy = blocked && busy && !closing;
  useEffect(() => {
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify(
          state.tabs.map((t) => ({ href: t.href, title: t.title })),
        ),
      );
    } catch {
      /* Tabs remain usable without storage. */
    }
  }, [storageKey, state.tabs]);
  useEffect(() => {
    if (!dirty && !busy) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, busy]);
  useLayoutEffect(() => {
    const nav = bar.current;
    // rc-tabs offers no prop for naming its tablist; the node itself is stable.
    nav?.querySelector('[role="tablist"]')?.setAttribute("aria-label", "已打开的页面");
    nav
      ?.querySelector('[aria-selected="true"]')
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [state.tabs, state.active]);
  const update = useCallback((id: string, meta: PageTabMeta) => {
    setState((current) => {
      const tab = current.tabs.find((t) => t.id === id);
      if (!tab) return current;
      const title = meta.title || tab.title;
      if (
        title === tab.title &&
        !!meta.dirty === !!tab.dirty &&
          !!meta.busy === !!tab.busy
          && !!meta.elementDirty === !!tab.elementDirty
          && !!meta.elementBusy === !!tab.elementBusy
      )
        return current;
      return {
        ...current,
        tabs: current.tabs.map((t) =>
          t.id === id ? { ...t, ...meta, title } : t,
        ),
      };
    });
  }, []);
  const remove = (id: string) => {
    let next = closeTab(state, id);
    if (!next.tabs.length) next = openTab(next, base + "/view");
    setState(next);
    if (state.active === id)
      void navigate(next.tabs.find((t) => t.id === next.active)!.href, {
        replace: true,
      });
    setClosing(null);
    strip.current
      ?.querySelector<HTMLElement>(`#workspace-tab-${next.active}`)
      ?.focus();
  };
  const requestClose = (tab: PageTab) => {
    if (tab.busy) {
      setNotice(`「${tab.title}」的操作正在进行，请完成后再关闭页面。`);
      return;
    }
    if (tab.dirty) setClosing(tab.id);
    else remove(tab.id);
  };
  const cancel = () => {
    setClosing(null);
    if (blocker.state === "blocked") blocker.reset();
  };
  const target = state.tabs.find((t) => t.id === closing);
  return (
    <div className="flex h-full flex-col">
      <div ref={strip} className="min-h-0 min-w-0 flex-1">
        <Tabs
          id="workspace"
          type="editable-card"
          size="small"
          hideAdd
          activeKey={state.active}
          // Child combinators only: pages rendered inside the panes have Tabs too.
          className="h-full [&>.ant-tabs-content-holder]:min-h-0 [&>.ant-tabs-content-holder>.ant-tabs-content]:h-full [&>.ant-tabs-content-holder>.ant-tabs-content>.ant-tabs-tabpane]:h-full"
          renderTabBar={(props, DefaultTabBar) => (
            // The bar holds only the strip and its notice, so these descendant
            // selectors cannot reach a page's own Tabs.
            <div ref={bar} className="workspace-tab-bar flex-none
                [&>.ant-tabs-nav]:h-control-lg [&>.ant-tabs-nav]:mb-0 [&>.ant-tabs-nav]:bg-surface-soft [&>.ant-tabs-nav]:px-3 [&>.ant-tabs-nav]:pt-1 [&>.ant-tabs-nav]:before:border-rule-soft
                [&_.ant-tabs-tab]:h-control-sm [&_.ant-tabs-tab]:m-0 [&_.ant-tabs-tab]:rounded-t-xs [&_.ant-tabs-tab]:rounded-b-none [&_.ant-tabs-tab]:border-transparent [&_.ant-tabs-tab]:bg-transparent [&_.ant-tabs-tab]:px-2 [&_.ant-tabs-tab]:py-0 [&_.ant-tabs-tab]:text-xs [&_.ant-tabs-tab]:leading-tight
                [&_.ant-tabs-tab+.ant-tabs-tab]:ml-1 [&_.ant-tabs-tab:not(.ant-tabs-tab-active):hover]:bg-rule-soft
                [&_.ant-tabs-tab.ant-tabs-tab-active]:border-rule-soft [&_.ant-tabs-tab.ant-tabs-tab-active]:border-b-surface [&_.ant-tabs-tab.ant-tabs-tab-active]:bg-surface
                [&_.ant-tabs-tab-remove]:ml-1 [&_.ant-tabs-tab-remove]:inline-flex [&_.ant-tabs-tab-remove]:items-center [&_.ant-tabs-tab-remove]:p-0 [&_.ant-tabs-tab-remove]:text-muted [&_.ant-tabs-tab-remove:hover]:text-ink">
              <DefaultTabBar {...props} />
              {notice && (
                <Alert
                  banner
                  type="warning"
                  role="status"
                  message={notice}
                  closable={{ closeIcon: true, "aria-label": "关闭提示" }}
                  onClose={() => setNotice("")}
                />
              )}
            </div>
          )}
          onChange={(key) => {
            const tab = state.tabs.find((t) => t.id === key);
            if (tab) void navigate(tab.href);
          }}
          onEdit={(targetKey, action) => {
            if (action === "remove" && typeof targetKey === "string") {
              const tab = state.tabs.find((t) => t.id === targetKey);
              if (tab) requestClose(tab);
            }
          }}
          items={state.tabs.map((tab) => {
            const area = new URL(tab.href, "http://local").pathname.split("/")[3];
            const Icon =
              {
                view: Network,
                relations: GitBranch,
                builder: Sparkles,
                mappings: Database,
                delivery: Rocket,
                settings: Settings,
              }[area] ?? Box;
            return {
              key: tab.id,
              children: tab.visited ? (
                <TabPanel tab={tab} active={state.active === tab.id} update={update} />
              ) : null,
              label: (
                <span
                  title={tab.title + (tab.dirty ? " · 未保存" : "")}
                  className="inline-flex min-w-0 items-center gap-2 text-xs whitespace-nowrap"
                >
                  <Icon className="size-icon-sm flex-none" />
                  <span className="max-w-tab-title truncate">{tab.title}</span>
                  {tab.dirty && (
                    <i
                      className="size-tab-dirty flex-none rounded-full bg-warning"
                      aria-label="未保存"
                    />
                  )}
                </span>
              ),
              closeIcon: (
                <span
                  role="button"
                  aria-label={`关闭 ${tab.title}`}
                  title="关闭页面"
                  className="inline-flex size-4 items-center justify-center rounded-xs"
                >
                  <X className="size-icon-xs" />
                </span>
              ),
            };
          })}
        />
      </div>
      <Modal
        open={!!closing || blocked}
        className="max-w-tab-confirm"
        title={blockingBusy ? "操作正在进行" : "有尚未保存的内容"}
        onCancel={cancel}
        footer={
          <div className="flex justify-end gap-2">
            <Button autoFocus onClick={cancel}>
              返回页面
            </Button>
            {!blockingBusy && (
              <Button
                type="primary"
                danger
                onClick={() => {
                  if (closing) remove(closing);
                  else if (blocker.state === "blocked") blocker.proceed();
                }}
              >
                放弃并{closing ? "关闭" : "离开"}
              </Button>
            )}
          </div>
        }
      >
        <p className="text-sm leading-base">
          {blockingBusy
            ? "请等待当前操作完成后再离开空间。"
            : target
              ? `关闭「${target.title}」将丢失未保存的修改。`
              : blocker.state === "blocked" && blocker.location.pathname.startsWith(base + "/")
                ? "离开当前内容将丢失尚未保存的修改，是否继续？"
                : "离开空间将丢失所有页签中尚未保存的内容，是否继续？"}
        </p>
      </Modal>
    </div>
  );
}
