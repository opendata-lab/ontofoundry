import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  createMemoryRouter,
  Link,
  RouterProvider,
  useParams,
  useRoutes,
  useSearchParams,
} from "react-router-dom";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePageTab } from "../hooks/usePageTab";
import { WorkspaceTabs } from "./WorkspaceTabs";

function TestPage() {
  const { typeId } = useParams();
  const [params] = useSearchParams();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  usePageTab({
    title: typeId ? `对象 ${typeId}` : undefined,
    dirty: !!typeId && !!text,
    busy,
  });
  return (
    <div className="test-scroll">
      <p>
        {typeId ?? "列表"} / {params.get("session") ?? "published"}
      </p>
      <input
        aria-label="页面输入"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button onClick={() => setBusy(!busy)}>切换忙碌</button>
      <Link to="../objects/b?session=s2">打开 B</Link>
    </div>
  );
}
vi.mock("./WorkspaceRoutes", () => ({
  WorkspaceRoutes: ({ href }: { href: string }) =>
    useRoutes(
      [
        { path: "objects/:typeId", element: <TestPage /> },
        { path: "*", element: <TestPage /> },
      ],
      href,
    ),
}));
function Shell() {
  const { workspaceId = "w" } = useParams();
  return (
    <>
      <Link to="/">离开空间</Link>
      <Link to="/workspaces/other/view">其他空间</Link>
      <WorkspaceTabs key={workspaceId} workspaceId={workspaceId} userId="u" />
    </>
  );
}
function show(path = "/workspaces/w/view") {
  const router = createMemoryRouter(
    [
      { path: "/", element: <div>空间目录</div> },
      { path: "/workspaces/:workspaceId/*", element: <Shell /> },
    ],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
  return router;
}
const tabs = () =>
  within(screen.getByRole("tablist", { name: "已打开的页面" }));
const input = () =>
  within(screen.getByRole("tabpanel")).getByRole("textbox", {
    name: "页面输入",
  });

beforeEach(() => {
  sessionStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});

describe("页签交互", () => {
  it("保存输入和滚动位置，冻结各页面参数，兼容相对链接和浏览器后退", async () => {
    const router = show("/workspaces/w/objects/a?session=s1");
    const original = input();
    fireEvent.change(original, { target: { value: "尚未保存" } });
    const scroll = original.parentElement!;
    scroll.scrollTop = 123;
    fireEvent.click(screen.getByRole("link", { name: "打开 B" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/workspaces/w/objects/b"),
    );
    expect(screen.getByRole("tabpanel")).toHaveTextContent("b / s2");
    expect(document.querySelector(".route-panel[hidden]")).toHaveTextContent(
      "a / s1",
    );
    fireEvent.change(input(), { target: { value: "B 的内容" } });
    fireEvent.click(tabs().getByRole("tab", { name: "对象 a 未保存" }));
    expect(input()).toBe(original);
    expect(input()).toHaveValue("尚未保存");
    expect(scroll.scrollTop).toBe(123);
    expect(tabs().getAllByRole("tab")).toHaveLength(2);
    await act(() => router.navigate(-1));
    expect(input()).toHaveValue("B 的内容");
    expect(tabs().getAllByRole("tab")).toHaveLength(2);
  });
  it("未保存关闭可取消，确认后移除且回到其他页", async () => {
    const router = show();
    await act(() => router.navigate("/workspaces/w/objects/a"));
    fireEvent.change(input(), { target: { value: "草稿" } });
    fireEvent.click(tabs().getByRole("button", { name: "关闭 对象 a" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("未保存");
    fireEvent.click(screen.getByRole("button", { name: "返回页面" }));
    expect(input()).toHaveValue("草稿");
    fireEvent.click(tabs().getByRole("button", { name: "关闭 对象 a" }));
    fireEvent.click(screen.getByRole("button", { name: "放弃并关闭" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/workspaces/w/view"),
    );
    expect(tabs().getAllByRole("tab")).toHaveLength(1);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("离开空间和刷新均保护后台草稿，取消不会丢失，确认后可离开", async () => {
    const router = show("/workspaces/w/objects/a");
    fireEvent.change(input(), { target: { value: "草稿" } });
    await act(() => router.navigate("/workspaces/w/view"));
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole("link", { name: "离开空间" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("离开空间");
    fireEvent.click(screen.getByRole("button", { name: "返回页面" }));
    expect(router.state.location.pathname).toBe("/workspaces/w/view");
    fireEvent.click(screen.getByRole("link", { name: "离开空间" }));
    fireEvent.click(screen.getByRole("button", { name: "放弃并离开" }));
    await screen.findByText("空间目录");
  });
  it("空间历史互不混用，返回后按需挂载，关闭最后一页回到本体视图", async () => {
    const router = show();
    await act(() => router.navigate("/workspaces/w/objects"));
    fireEvent.click(screen.getByRole("link", { name: "其他空间" }));
    expect(tabs().getAllByRole("tab")).toHaveLength(1);
    await act(() => router.navigate("/workspaces/w/view"));
    expect(tabs().getAllByRole("tab")).toHaveLength(2);
    expect(document.querySelectorAll(".route-panel")).toHaveLength(1);
    fireEvent.click(tabs().getByRole("button", { name: "关闭 业务对象" }));
    fireEvent.click(tabs().getByRole("button", { name: "关闭 本体视图" }));
    expect(tabs().getAllByRole("tab")).toHaveLength(1);
    expect(router.state.location.pathname).toBe("/workspaces/w/view");
  });
  it("请求进行中不可关闭或跳转，不丢弃在途操作", async () => {
    const router = show();
    fireEvent.click(screen.getByRole("button", { name: "切换忙碌" }));
    await act(() => router.navigate("/workspaces/w/objects"));
    expect(screen.getByRole("dialog")).toHaveTextContent("操作正在进行");
    expect(router.state.location.pathname).toBe("/workspaces/w/view");
    expect(screen.queryByRole("button", { name: "放弃并离开" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "返回页面" }));
    fireEvent.click(tabs().getByRole("button", { name: "关闭 本体视图" }));
    expect(screen.getByRole("status")).toHaveTextContent("操作正在进行");
  });
});
