import { describe, expect, it } from "vitest";
import {
  closeTab,
  openTab,
  restoreTabs,
  tabKey,
  type TabState,
} from "./pageTabs";
const base = "/workspaces/w";
const empty = (): TabState => ({ tabs: [], active: "", recent: [] });

describe("路由页签身份", () => {
  it("复用同一页面，保留不同会话及数据库实例", () => {
    let s = openTab(empty(), base + "/objects/a?session=s1&source=document");
    const id = s.active;
    s = openTab(s, base + "/objects/a?source=database&session=s1");
    expect(s.tabs).toHaveLength(1);
    expect(s.active).toBe(id);
    s = openTab(s, base + "/objects/a?session=s2");
    s = openTab(s, base + "/objects/a");
    expect(s.tabs).toHaveLength(3);
    expect(tabKey(base + "/objects/a/instances/database?key=1")).not.toBe(
      tabKey(base + "/objects/a/instances/database?key=2"),
    );
  });
  it("创建会话与首次保存复用页签，但切换已有会话分别保留", () => {
    let s = openTab(empty(), base + "/builder");
    const id = s.active;
    s = openTab(s, base + "/builder?session=s1", true);
    expect(s.tabs).toHaveLength(1);
    expect(s.active).toBe(id);
    s = openTab(s, base + "/builder?session=s2", true);
    expect(s.tabs).toHaveLength(2);
    s = openTab(s, base + "/objects/new/edit?session=s1");
    const editor = s.active;
    s = openTab(s, base + "/objects/a/edit?session=s1", true);
    expect(s.active).toBe(editor);
    expect(s.tabs).toHaveLength(3);
  });
  it("关闭当前页返回最近访问页，关闭其他页不改变当前页", () => {
    let s = openTab(empty(), base + "/view");
    const home = s.active;
    s = openTab(s, base + "/objects");
    const catalog = s.active;
    s = openTab(s, base + "/builder");
    s = openTab(s, base + "/view");
    s = closeTab(s, catalog);
    expect(s.active).toBe(home);
    s = closeTab(s, home);
    expect(s.tabs.find((t) => t.id === s.active)?.href).toBe(base + "/builder");
  });
  it("历史只恢复本空间链接，不挂载后台页面，不恢复表单或不可信地址", () => {
    const state = restoreTabs(
      JSON.stringify([
        { href: base + "/objects", dirty: true, title: "old" },
        { href: "/workspaces/other/objects" },
        { href: "https://example.com/" },
        { href: base + "/../../other" },
        { href: base + "/objects" },
      ]),
      base,
    );
    expect(state.tabs).toHaveLength(1);
    expect(state.tabs[0]).toMatchObject({ visited: false, title: "old" });
    expect(state.tabs[0].dirty).toBeUndefined();
    expect(restoreTabs("broken", base).tabs).toEqual([]);
  });
});
