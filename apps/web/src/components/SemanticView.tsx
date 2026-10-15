import {
  Box,
  Braces,
  ChevronDown,
  LocateFixed,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sparkles,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePageActive } from "../hooks/usePageTab";
import type { LegacyDraft, TypeGraph } from "../api/types";
import type { ElementRequest } from "../lib/elementInspector";
import {
  semanticCanvas,
  semanticResources,
  type SemanticResource,
} from "../lib/semanticExplorer";
import { OntologyGraph, type SelectedGraphItem } from "./OntologyGraph";
import "../styles/semantic-view.css";

const STORAGE_KEY = "ontofoundry.semantic.explorer.collapsed";
const groups = [
  { kind: "object", name: "业务对象", icon: Box },
  { kind: "relation", name: "本体关系", icon: Workflow },
  { kind: "value", name: "值类型", icon: Braces },
  { kind: "rule", name: "规则", icon: Sparkles },
] as const;
export function SemanticView({
  graph,
  model,
  onOpen,
  resourceError,
}: {
  graph: TypeGraph;
  model?: LegacyDraft | null;
  onOpen: (request: ElementRequest) => void;
  resourceError?: string;
}) {
  const active = usePageActive();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored === null ? window.innerWidth < 700 : stored === "true";
    } catch {
      return window.innerWidth < 700;
    }
  });
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState({ left: 0, top: 0 });
  const filter = useRef<HTMLInputElement>(null);
  const tree = useRef<HTMLDivElement>(null);
  const menuRoot = useRef<HTMLDivElement>(null);
  const resources = useMemo(
    () => semanticResources(graph, model),
    [graph, model],
  );
  const canvas = useMemo(
    () => semanticCanvas(graph, resources),
    [graph, resources],
  );
  const selection = resources.find((r) => r.id === selected);
  const graphSelection =
    selection?.selection?.category === "node" &&
    selection.selection.item.kind === "link_type"
      ? {
          category: "edge" as const,
          item: canvas.edges.find((e) => e.id === selection.id)!,
        }
      : (selection?.selection ?? null);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (
        active &&
        event.key === "Escape" &&
        !document.querySelector("dialog[open]")
      ) {
        if (menu) setMenu(null);
        else if (selected) setSelected(null);
        else setQuery("");
      }
    };
    const outside = (event: PointerEvent) => {
      if (!menuRoot.current?.contains(event.target as Node)) setMenu(null);
    };
    document.addEventListener("keydown", escape);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", escape);
      document.removeEventListener("pointerdown", outside);
    };
  }, [selected, menu, active]);
  useEffect(() => {
    if (!menu) return;
    const frame = requestAnimationFrame(() =>
      menuRoot.current
        ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
        ?.focus(),
    );
    return () => cancelAnimationFrame(frame);
  }, [menu]);
  const collapse = (value: boolean) => {
    setCollapsed(value);
    setMenu(null);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* Browsing remains available when storage is blocked. */
    }
  };
  const select = (resource: SemanticResource, fromGraph = false) => {
    setSelected(resource.id);
    setMenu(null);
    if (fromGraph) {
      setQuery("");
      setClosed((previous) => {
        const next = new Set(previous);
        next.delete(resource.kind);
        return next;
      });
      requestAnimationFrame(() =>
        Array.from(
          tree.current?.querySelectorAll<HTMLElement>("[data-resource]") ?? [],
        )
          .find((row) => row.dataset.resource === resource.id)
          ?.scrollIntoView?.({ block: "nearest" }),
      );
    }
  };
  const graphSelect = (item: SelectedGraphItem) => {
    if (!item) {
      setSelected(null);
      return;
    }
    const id =
      item.category === "edge"
        ? (item.item.link_type_id ?? item.item.id)
        : item.item.id;
    const resource = resources.find((r) => r.id === id);
    if (resource) select(resource, true);
  };
  const openResource = (resource?: SemanticResource) => {
    setMenu(null);
    if (
      resource?.detail &&
      !(resource.kind === "value" && resource.id.startsWith("builtin:"))
    )
      onOpen(resource.detail);
  };
  const objects = resources.filter((r) => r.kind === "object"),
    relations = resources.filter((r) => r.kind === "relation");
  const menuResource = resources.find((r) => r.id === menu);
  return (
    <div className="semantic-view-workbench">
      <aside
        className={`semantic-explorer${collapsed ? " is-collapsed" : ""}`}
        aria-label="资源管理器"
      >
        <header>
          <h2>资源管理器</h2>
          <button
            type="button"
            className="icon-button"
            aria-label={collapsed ? "展开资源管理器" : "收起资源管理器"}
            aria-expanded={!collapsed}
            aria-controls="semantic-explorer-content"
            title={collapsed ? "展开资源管理器" : "收起资源管理器"}
            onClick={() => collapse(!collapsed)}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
          </button>
        </header>
        {collapsed && (
          <div className="semantic-explorer-rail">
            <button
              type="button"
              className="icon-button"
              aria-label="展开并筛选名称"
              onClick={() => {
                collapse(false);
                requestAnimationFrame(() => filter.current?.focus());
              }}
            >
              <Search size={16} />
            </button>
            <span>资源管理器</span>
          </div>
        )}
        <div
          id="semantic-explorer-content"
          className="semantic-explorer-content"
          hidden={collapsed}
        >
          <div className="semantic-filter-wrap">
            <label className="semantic-filter">
              <Search size={15} />
              <input
                ref={filter}
                type="search"
                placeholder="名称筛选"
                aria-label="名称筛选"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setClosed(new Set());
                  setMenu(null);
                }}
              />
              {query && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label="清空名称筛选"
                  onClick={() => {
                    setQuery("");
                    filter.current?.focus();
                  }}
                >
                  <X size={14} />
                </button>
              )}
            </label>
          </div>
          <div
            className="semantic-tree"
            ref={tree}
            aria-label="本体资源"
            onScroll={() => setMenu(null)}
            onKeyDown={(e) => {
              if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key))
                return;
              const buttons = Array.from(
                e.currentTarget.querySelectorAll<HTMLButtonElement>(
                  ".semantic-group-heading, .semantic-item-select",
                ),
              ).filter((b) => !b.closest("[hidden]"));
              const at = buttons.indexOf(e.target as HTMLButtonElement);
              if (at < 0) return;
              e.preventDefault();
              buttons[
                e.key === "Home"
                  ? 0
                  : e.key === "End"
                    ? buttons.length - 1
                    : (at + (e.key === "ArrowDown" ? 1 : -1) + buttons.length) %
                      buttons.length
              ]?.focus();
            }}
          >
            {groups.map((group) => {
              const items = resources.filter((r) => r.kind === group.kind);
              if (!items.length) return null;
              const filtered = items.filter((r) =>
                [r.name, r.technical, r.subtitle]
                  .join(" ")
                  .toLocaleLowerCase()
                  .includes(query.toLocaleLowerCase()),
              );
              const expanded = !closed.has(group.kind),
                Icon = group.icon;
              return (
                <section
                  key={group.kind}
                  className={`semantic-group${expanded ? " is-open" : ""}`}
                >
                  <button
                    type="button"
                    className="semantic-group-heading"
                    aria-expanded={expanded}
                    aria-controls={`semantic-group-${group.kind}`}
                    onClick={() => {
                      setClosed((previous) => {
                        const next = new Set(previous);
                        if (next.has(group.kind)) next.delete(group.kind);
                        else next.add(group.kind);
                        return next;
                      });
                      setMenu(null);
                    }}
                  >
                    <ChevronDown size={13} />
                    <span>{group.name}</span>
                    <small>
                      {query ? `${filtered.length} / ` : ""}
                      {items.length}
                    </small>
                  </button>
                  <div
                    id={`semantic-group-${group.kind}`}
                    className="semantic-group-items"
                    hidden={!expanded}
                  >
                    {filtered.map((resource) => (
                      <div
                        key={resource.id}
                        data-resource={resource.id}
                        className={`semantic-tree-row${selected === resource.id ? " is-selected" : ""}`}
                      >
                        <button
                          type="button"
                          className="semantic-item-select"
                          aria-pressed={selected === resource.id}
                          title={[resource.technical, resource.subtitle]
                            .filter(Boolean)
                            .join(" · ")}
                          onClick={() => select(resource)}
                        >
                          <Icon size={15} />
                          <span>
                            <span className="semantic-item-name">
                              {resource.name}
                            </span>
                            {resource.subtitle && (
                              <small>{resource.subtitle}</small>
                            )}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="icon-button semantic-item-menu"
                          aria-label={`${resource.name}的操作`}
                          aria-haspopup="menu"
                          aria-expanded={menu === resource.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            const bounds =
                              e.currentTarget.getBoundingClientRect();
                            setMenuPosition({
                              left: Math.min(
                                window.innerWidth - 164,
                                bounds.right + 4,
                              ),
                              top: Math.min(
                                window.innerHeight - 130,
                                bounds.top,
                              ),
                            });
                            setMenu(menu === resource.id ? null : resource.id);
                          }}
                        >
                          <MoreHorizontal size={17} />
                        </button>
                      </div>
                    ))}
                    {!filtered.length && (
                      <p className="semantic-empty-group">无匹配项</p>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
          {resourceError && (
            <p role="status" className="semantic-resource-error">
              {resourceError}
            </p>
          )}
        </div>
        <footer hidden={collapsed}>
          <span>
            {objects.length} 个对象 · {relations.length} 个关系
          </span>
          <span>
            <kbd>Esc</kbd> 清除
          </span>
        </footer>
      </aside>
      <section className="semantic-canvas" aria-label="语义关系画布">
        <OntologyGraph
          graph={canvas}
          query=""
          selection={graphSelection}
          viewportKey={collapsed}
          semantic
          onSelect={graphSelect}
          onOpen={(item) => {
            if (!item) return;
            const id =
              item.category === "edge"
                ? (item.item.link_type_id ?? item.item.id)
                : item.item.id;
            openResource(resources.find((r) => r.id === id));
          }}
        />
        {selection && (
          <div className="semantic-selection-chip">
            <strong>{selection.name}</strong>
            {!(
              selection.kind === "value" && selection.id.startsWith("builtin:")
            ) && (
              <button
                type="button"
                className="icon-button"
                aria-label="打开选中资源详情"
                title="打开详情"
                onClick={() => openResource(selection)}
              >
                <PanelLeftOpen size={15} />
              </button>
            )}
            <button
              type="button"
              className="icon-button"
              aria-label="清除选择"
              title="清除选择 · Esc"
              onClick={() => setSelected(null)}
            >
              <X size={15} />
            </button>
          </div>
        )}
        <div className="semantic-status-chip" role="status">
          显示 {objects.length} / {objects.length} 个对象 · {relations.length} /{" "}
          {relations.length} 个关系
        </div>
      </section>
      {menuResource && (
        <div
          className="semantic-context-menu"
          ref={menuRoot}
          role="menu"
          style={menuPosition}
          aria-label="资源操作"
          onKeyDown={(e) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key))
              return;
            e.preventDefault();
            const items = Array.from(
              e.currentTarget.querySelectorAll<HTMLButtonElement>(
                "button:not(:disabled)",
              ),
            );
            const at = items.indexOf(e.target as HTMLButtonElement);
            items[
              e.key === "Home"
                ? 0
                : e.key === "End"
                  ? items.length - 1
                  : (at + (e.key === "ArrowDown" ? 1 : -1) + items.length) %
                    items.length
            ]?.focus();
          }}
        >
          <button
            type="button"
            role="menuitem"
            disabled={
              menuResource.kind === "value" &&
              menuResource.id.startsWith("builtin:")
            }
            onClick={() => openResource(menuResource)}
          >
            <PanelLeftOpen size={15} />
            打开详情
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => select(menuResource, true)}
          >
            <LocateFixed size={15} />
            在图中定位
          </button>
          {menuResource.kind === "object" && (
            <button
              type="button"
              role="menuitem"
              disabled
              title="对象保存范围不包含新关系，请在「本体构建」中添加关系。"
            >
              ＋ 添加关系
            </button>
          )}
        </div>
      )}
    </div>
  );
}
