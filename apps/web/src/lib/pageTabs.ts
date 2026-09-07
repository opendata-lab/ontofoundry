export type PageTab = {
  id: string;
  href: string;
  title: string;
  visited: boolean;
  dirty?: boolean;
  busy?: boolean;
};
export type TabState = { tabs: PageTab[]; active: string; recent: string[] };

export function tabKey(href: string) {
  const url = new URL(href, "http://local");
  return JSON.stringify([
    url.pathname.replace(/\/$/, ""),
    url.searchParams.get("session"),
    url.searchParams.get("key"),
  ]);
}

export function tabTitle(href: string) {
  const path = new URL(href, "http://local").pathname.split("/").slice(3);
  if (path.includes("edit")) return path[1] === "new" ? "新建本体" : "编辑本体";
  if (path.includes("instances"))
    return path.length > 3 ? "实例详情" : "实例列表";
  if (path.length > 1) return path[0] === "relations" ? "关系详情" : "本体详情";
  return (
    {
      view: "本体视图",
      objects: "业务对象",
      relations: "本体关系",
      builder: "本体自动构建",
      mappings: "数据映射",
      delivery: "发布与服务",
      settings: "空间设置",
    }[path[0]] ?? "本体视图"
  );
}

export function isTabPromotion(from: string, to: string) {
  const a = new URL(from, "http://local");
  const b = new URL(to, "http://local");
  if (a.pathname === b.pathname && /\/(builder|delivery)$/.test(a.pathname))
    return !a.searchParams.has("session") && b.searchParams.has("session");
  return (
    a.pathname.endsWith("/new/edit") &&
    b.pathname.endsWith("/edit") &&
    a.pathname.split("/").slice(0, -2).join("/") ===
      b.pathname.split("/").slice(0, -2).join("/") &&
    a.searchParams.get("session") === b.searchParams.get("session")
  );
}

export function openTab(
  state: TabState,
  href: string,
  replace = false,
): TabState {
  const found = state.tabs.find((t) => tabKey(t.href) === tabKey(href));
  const previous = state.tabs.find((t) => t.id === state.active);
  const promoted =
    !found && replace && previous && isTabPromotion(previous.href, href)
      ? previous
      : undefined;
  const tab = found ??
    promoted ?? {
      id: crypto.randomUUID(),
      href,
      title: tabTitle(href),
      visited: true,
    };
  return {
    tabs:
      found || promoted
        ? state.tabs.map((t) =>
            t.id === tab.id ? { ...t, href, visited: true } : t,
          )
        : [...state.tabs, tab],
    active: tab.id,
    recent: [...state.recent.filter((id) => id !== tab.id), tab.id],
  };
}

export function closeTab(state: TabState, id: string): TabState {
  const tabs = state.tabs.filter((t) => t.id !== id);
  const recent = state.recent.filter((value) => value !== id);
  return {
    tabs,
    recent,
    active:
      state.active === id ? (recent.at(-1) ?? tabs[0]?.id ?? "") : state.active,
  };
}

// Persist navigation only. Unsaved forms, credentials and model data stay in memory.
export function restoreTabs(raw: string | null, base: string): TabState {
  let state: TabState = { tabs: [], active: "", recent: [] };
  try {
    const entries: unknown = JSON.parse(raw ?? "[]");
    if (Array.isArray(entries))
      for (const item of entries) {
        if (typeof item?.href !== "string" || !item.href.startsWith(base + "/"))
          continue;
        const url = new URL(item.href, "http://local");
        if (!url.pathname.startsWith(base + "/")) continue;
        state = openTab(state, item.href);
        if (typeof item.title === "string" && item.title.trim()) {
          state.tabs = state.tabs.map((t) =>
            t.id === state.active
              ? { ...t, title: item.title.slice(0, 160) }
              : t,
          );
        }
      }
  } catch {
    /* Storage may be unavailable or from an older build. */
  }
  return { ...state, tabs: state.tabs.map((t) => ({ ...t, visited: false })) };
}
