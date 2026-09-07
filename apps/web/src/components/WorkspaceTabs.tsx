import {
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
  isTabPromotion,
  openTab,
  restoreTabs,
  type PageTab,
} from "../lib/pageTabs";
import { LoadingSurface } from "./AsyncState";
import { WorkspaceRoutes } from "./WorkspaceRoutes";
import "../styles/page-tabs.css";

function TabPanel({
  tab,
  active,
  update,
}: {
  tab: PageTab;
  active: boolean;
  update: (id: string, meta: PageTabMeta) => void;
}) {
  const setMeta = useCallback(
    (meta: PageTabMeta) => update(tab.id, meta),
    [update, tab.id],
  );
  const context = useMemo(
    () => ({ active, update: setMeta }),
    [active, setMeta],
  );
  return (
    <section
      className="route-panel"
      id={`panel-${tab.id}`}
      role="tabpanel"
      aria-labelledby={`tab-${tab.id}`}
      hidden={!active}
      inert={!active}
    >
      <PageTabContext.Provider value={context}>
        <Suspense fallback={<LoadingSurface label="正在打开页面…" />}>
          <WorkspaceRoutes href={tab.href} />
        </Suspense>
      </PageTabContext.Provider>
    </section>
  );
}

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
  const [seen, setSeen] = useState(location.key + href);
  if (seen !== location.key + href) {
    setSeen(location.key + href);
    setState((current) => openTab(current, href, navigationType === "REPLACE"));
  }
  const strip = useRef<HTMLDivElement>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const busy = state.tabs.some((t) => t.busy);
  const dirty = state.tabs.some((t) => t.dirty);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (
      nextLocation.pathname === currentLocation.pathname &&
      nextLocation.state?.tabOperation === "session-created"
    )
      return false;
    if (
      busy &&
      !isTabPromotion(createPath(currentLocation), createPath(nextLocation))
    )
      return true;
    return dirty && !nextLocation.pathname.startsWith(base + "/");
  });
  const blocked = blocker.state === "blocked";
  useEffect(() => {
    if (closing || blocked) dialog.current?.showModal();
    else dialog.current?.close();
  }, [closing, blocked]);
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
    if (tab.busy || busy) {
      setNotice("操作正在进行，请完成后再关闭页面。");
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
    <>
      <div
        className="route-tabs"
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
              className={
                "route-tab" + (state.active === tab.id ? " is-active" : "")
              }
            >
              <button
                id={`tab-${tab.id}`}
                role="tab"
                aria-controls={`panel-${tab.id}`}
                aria-selected={state.active === tab.id}
                tabIndex={state.active === tab.id ? 0 : -1}
                title={tab.title + (tab.dirty ? " · 未保存" : "")}
                onClick={() => void navigate(tab.href)}
              >
                <Icon size={14} />
                <span>{tab.title}</span>
                {tab.dirty && <i className="tab-dirty" aria-label="未保存" />}
              </button>
              <button
                className="tab-close"
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
        <div className="tab-notice" role="status">
          {notice}
          <button onClick={() => setNotice("")} aria-label="关闭提示">
            <X size={14} />
          </button>
        </div>
      )}
      <div className="route-panels">
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
      <dialog
        ref={dialog}
        className="ref-dialog tab-confirm"
        aria-labelledby="tab-confirm-title"
        onCancel={(e) => {
          e.preventDefault();
          cancel();
        }}
      >
        <header>
          <h2 id="tab-confirm-title">
            {busy ? "操作正在进行" : "有尚未保存的内容"}
          </h2>
        </header>
        <p>
          {busy
            ? "请等待当前操作完成后再切换或关闭页面。"
            : target
              ? `关闭「${target.title}」将丢失未保存的修改。`
              : "离开空间将丢失所有页签中尚未保存的内容，是否继续？"}
        </p>
        <footer className="row-actions">
          <button
            className="button button--secondary"
            autoFocus
            onClick={cancel}
          >
            返回页面
          </button>
          {!busy && (
            <button
              className="button button--primary"
              onClick={() => {
                if (closing) remove(closing);
                else if (blocker.state === "blocked") blocker.proceed();
              }}
            >
              放弃并{closing ? "关闭" : "离开"}
            </button>
          )}
        </footer>
      </dialog>
    </>
  );
}
