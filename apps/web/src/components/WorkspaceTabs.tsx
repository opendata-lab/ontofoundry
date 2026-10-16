import { Alert, Button, Modal } from "antd";
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
// or not, re-rendered on each menu switch.
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
    <section
      className="h-full min-w-0 overflow-auto"
      id={`panel-${tab.id}`}
      role="tabpanel"
      aria-labelledby={`tab-${tab.id}`}
      hidden={!active}
      inert={!active}
    >
      <LocationContext.Provider value={location}>
        <PageTabContext.Provider value={context}>
          <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
            <WorkspaceRoutes href={tab.href} />
          </Suspense>
        </PageTabContext.Provider>
      </LocationContext.Provider>
    </section>
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
    strip.current
      ?.querySelector('[aria-selected="true"]')
      ?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  }, [state.active]);
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
      ?.querySelector<HTMLButtonElement>(`#tab-${next.active}`)
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
      <div
        className="flex min-w-0 flex-[0_0_36px] gap-[3px] overflow-x-auto border-b border-rule-soft bg-[#f3f5f7] px-2.5 pt-1 [scrollbar-width:thin]"
        ref={strip}
        role="tablist"
        aria-label="已打开的页面"
        onKeyDown={(e) => {
          if (
            !(e.target instanceof HTMLElement) ||
            e.target.getAttribute("role") !== "tab"
          )
            return;
          const targetId = e.target.id;
          const index = state.tabs.findIndex((t) => `tab-${t.id}` === targetId);
          const nextIndex =
            e.key === "ArrowRight"
              ? (index + 1) % state.tabs.length
              : e.key === "ArrowLeft"
                ? (index - 1 + state.tabs.length) % state.tabs.length
                : e.key === "Home"
                  ? 0
                  : e.key === "End"
                    ? state.tabs.length - 1
                    : -1;
          if (nextIndex >= 0) {
            e.preventDefault();
            const tab = state.tabs[nextIndex];
            void navigate(tab.href);
            strip.current
              ?.querySelector<HTMLButtonElement>(`#tab-${tab.id}`)
              ?.focus();
          } else if (e.key === "Delete") {
            e.preventDefault();
            requestClose(state.tabs[index]);
          }
        }}
      >
        {state.tabs.map((tab) => {
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
          return (
            <div
              key={tab.id}
              className={`flex flex-none items-center rounded-t-xs border border-b-0 ${state.active === tab.id ? "border-rule-soft bg-surface text-accent" : "border-transparent text-muted hover:bg-[#eaf0f6]"}`}
            >
              <button
                id={`tab-${tab.id}`}
                role="tab"
                aria-controls={`panel-${tab.id}`}
                aria-selected={state.active === tab.id}
                tabIndex={state.active === tab.id ? 0 : -1}
                title={tab.title + (tab.dirty ? " · 未保存" : "")}
                onClick={() => void navigate(tab.href)}
                className="flex h-[30px] min-w-0 items-center gap-[7px] border-0 bg-transparent py-0 pr-2 pl-3 text-xs whitespace-nowrap text-inherit focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
              >
                <Icon size={14} className="flex-none" />
                <span className="max-w-[180px] truncate">{tab.title}</span>
                {tab.dirty && <i className="size-[5px] flex-none rounded-full bg-[#d58b20]" aria-label="未保存" />}
              </button>
              <button
                className="mr-[5px] grid size-5 place-items-center rounded-[3px] border-0 bg-transparent p-0 text-muted hover:bg-[#e5eaf0] hover:text-ink focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
                aria-label={`关闭 ${tab.title}`}
                title="关闭页面"
                onClick={() => requestClose(tab)}
              >
                <X size={12} />
              </button>
            </div>
          );
        })}
      </div>
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
      <div className="relative min-h-0 min-w-0 flex-1">
        {state.tabs
          .filter((t) => t.visited)
          .map((tab) => (
            <TabPanel
              key={tab.id}
              tab={tab}
              active={state.active === tab.id}
              update={update}
            />
          ))}
      </div>
      <Modal
        open={!!closing || blocked}
        width={420}
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
        <p className="text-[13px] leading-[1.7]">
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
