import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, workspaceRequest } from "../api/client";
import type { Member, User, Workspace } from "../api/types";
import { copyText } from "../lib/clipboard";
import { workspace as makeWorkspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { SettingsPage } from "./SettingsPage";

const context = vi.hoisted(() => ({
  workspace: {} as Workspace,
  user: {} as User,
  refresh: vi.fn(),
}));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => context,
}));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn() }));
vi.mock("../lib/clipboard", () => ({ copyText: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      updateWorkspace: vi.fn(),
      members: vi.fn(),
      addMember: vi.fn(),
      updateMemberRole: vi.fn(),
      removeMember: vi.fn(),
      searchWorkspaceUsers: vi.fn(),
    },
    workspaceRequest: vi.fn(),
  };
});

const adminUser: User = {
  id: "u1",
  username: "linxiao",
  display_name: "林晓",
  email: null,
  is_platform_admin: false,
  local_account: true,
};

const defaultMembers: Member[] = [
  {
    id: 1,
    user_id: "u1",
    username: "linxiao",
    display_name: "林晓",
    role: "admin",
    last_login_at: "2026-11-12T08:00:00Z",
  },
  {
    id: 2,
    user_id: "u3",
    username: "chenning",
    display_name: "陈宁",
    role: "member",
    last_login_at: null,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  context.user = adminUser;
  context.workspace = makeWorkspace({
    id: "w1",
    slug: "xinghe-retail",
    name: "测试空间",
    description: "虚构的零售示例",
  });
  vi.mocked(api.members).mockResolvedValue({ items: defaultMembers });
  vi.mocked(api.updateWorkspace).mockResolvedValue(context.workspace);
  vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({ items: [] });
  vi.mocked(copyText).mockResolvedValue(undefined);
});

afterEach(cleanup);

function show() {
  return renderWithProviders(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

async function openRoleSelect(name: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name }));
  // Options of the most recently opened dropdown.
  return (label: string) =>
    screen.findAllByText(label, { selector: ".ant-select-item-option-content" }).then((all) => all.at(-1)!);
}

describe("空间设置", () => {
  it("展示空间信息与成员两个面板，不再包含 DataAgent 连通性", async () => {
    show();

    expect(screen.getByRole("heading", { name: "空间设置" })).toBeInTheDocument();
    expect(screen.getByText("空间信息")).toBeInTheDocument();
    expect(screen.getByText("空间公开")).toBeInTheDocument();
    expect(screen.getByText("空间成员")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "对平台全部登录用户公开" })).not.toBeChecked();
    expect(screen.getByText("xinghe-retail")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "空间名称" })).toHaveValue("测试空间");
    expect(screen.getByRole("textbox", { name: "说明" })).toHaveValue("虚构的零售示例");
    expect(screen.getByRole("button", { name: "保存空间信息" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "重置" })).not.toBeInTheDocument();

    expect(await screen.findByText("linxiao")).toBeInTheDocument();
    expect(screen.getByText("2 人")).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "用户名",
      "角色",
      "操作",
    ]);
    const selfRow = screen.getByText("linxiao").closest("tr")!;
    expect(within(selfRow).getByText("（当前用户）")).toBeInTheDocument();
    expect(within(selfRow).queryByText("（尚未登录）")).not.toBeInTheDocument();
    const pendingRow = screen.getByText("chenning").closest("tr")!;
    expect(within(pendingRow).getByText("（尚未登录）")).toBeInTheDocument();
    expect(screen.queryByText("林晓")).not.toBeInTheDocument();
    expect(screen.getByText(/空间为私有：仅以下成员和平台超级管理员可访问/)).toBeInTheDocument();
    // The add bar stays collapsed until asked for.
    expect(screen.queryByRole("combobox", { name: "搜索已有用户" })).not.toBeInTheDocument();

    expect(screen.queryByText("DataAgent 连通性")).not.toBeInTheDocument();
    expect(workspaceRequest).not.toHaveBeenCalled();
    expect(api.members).toHaveBeenCalledWith("w1");
  });

  it("非管理员进入空间设置时展示 403 无权限页", () => {
    context.workspace = makeWorkspace({ role: "viewer" });
    show();
    expect(screen.getByText("无权访问")).toBeInTheDocument();
    expect(screen.getByText("只有该工作空间的管理员可以打开「空间设置」。")).toBeInTheDocument();
    expect(api.members).not.toHaveBeenCalled();
  });

  it("修改后才能保存或重置，保存后显示已保存并在再次修改时清除", async () => {
    show();
    const name = screen.getByRole("textbox", { name: "空间名称" });
    const save = screen.getByRole("button", { name: "保存空间信息" });

    fireEvent.change(name, { target: { value: "改名中" } });
    expect(save).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "重置" }));
    expect(name).toHaveValue("测试空间");
    expect(save).toBeDisabled();
    expect(screen.queryByRole("button", { name: "重置" })).not.toBeInTheDocument();

    fireEvent.change(name, { target: { value: "   " } });
    fireEvent.click(save);
    expect(await screen.findByText("请填写空间名称")).toBeInTheDocument();
    expect(api.updateWorkspace).not.toHaveBeenCalled();

    fireEvent.change(name, { target: { value: "  星河零售  " } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.updateWorkspace).toHaveBeenCalledWith("w1", {
        name: "星河零售",
        description: "虚构的零售示例",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("已保存");
    expect(context.refresh).toHaveBeenCalledTimes(1);
    expect(save).toBeDisabled();
    // The workspace has not been refreshed yet; the saved value must stay.
    expect(name).toHaveValue("星河零售");

    fireEvent.change(screen.getByRole("textbox", { name: "说明" }), { target: { value: "新说明" } });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(save).toBeEnabled();
  });

  it("保存失败时浮动报错并保留修改", async () => {
    vi.mocked(api.updateWorkspace).mockRejectedValueOnce(new ApiError("名称已被占用", 409, "CONFLICT"));
    show();
    fireEvent.change(screen.getByRole("textbox", { name: "空间名称" }), { target: { value: "重名空间" } });
    fireEvent.click(screen.getByRole("button", { name: "保存空间信息" }));
    expect(await screen.findByText("名称已被占用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存空间信息" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "空间名称" })).toHaveValue("重名空间");
  });

  it("设为公开失败时确认框保持打开", async () => {
    vi.mocked(api.updateWorkspace).mockRejectedValueOnce(new ApiError("无权修改", 403, "FORBIDDEN"));
    show();
    fireEvent.click(await screen.findByRole("switch", { name: "对平台全部登录用户公开" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "确认公开" }));
    expect(await screen.findByText("无权修改")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(context.refresh).not.toHaveBeenCalled();
  });

  it("复制空间标识", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "复制" }));
    await waitFor(() => expect(copyText).toHaveBeenCalledWith("xinghe-retail"));
    expect(await screen.findByText("已复制空间标识")).toBeInTheDocument();
  });

  it("开启空间公开需弹窗确认后提交 PATCH，关闭时直接生效", async () => {
    show();
    fireEvent.click(await screen.findByRole("switch", { name: "对平台全部登录用户公开" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("确认将「测试空间」设为公开？")).toBeInTheDocument();
    expect(api.updateWorkspace).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "确认公开" }));
    await waitFor(() => {
      expect(api.updateWorkspace).toHaveBeenCalledWith("w1", { is_public: true });
      expect(context.refresh).toHaveBeenCalledTimes(1);
    });

    cleanup();
    vi.clearAllMocks();
    context.workspace = makeWorkspace({ id: "w1", name: "测试空间", is_public: true, visibility: "public" });
    vi.mocked(api.members).mockResolvedValue({ items: defaultMembers });
    vi.mocked(api.updateWorkspace).mockResolvedValue(context.workspace);
    show();
    expect(screen.getByText(/空间已公开：所有登录用户可阅读全部内容/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("switch", { name: "对平台全部登录用户公开" }));
    await waitFor(() => {
      expect(api.updateWorkspace).toHaveBeenCalledWith("w1", { is_public: false });
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("内联添加栏按用户名搜索、选择干净的角色并添加成员", async () => {
    vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({
      items: [
        { id: "u2", username: "lisi", display_name: "李四", last_login_at: null },
        { id: "u3", username: "chenning", display_name: "陈宁", last_login_at: null },
      ],
    });
    vi.mocked(api.addMember).mockResolvedValue({
      id: 3,
      user_id: "u2",
      username: "lisi",
      display_name: "李四",
      role: "viewer",
      last_login_at: null,
    });

    show();
    await screen.findByText("linxiao");
    const openButton = screen.getByRole("button", { name: /添加成员/ });
    fireEvent.click(openButton);
    expect(openButton).toBeDisabled();

    const search = screen.getByRole("combobox", { name: "搜索已有用户" });
    fireEvent.change(search, { target: { value: "lisi" } });
    await waitFor(() => expect(api.searchWorkspaceUsers).toHaveBeenCalledWith("w1", "lisi"));
    const option = await screen.findByText("lisi", { selector: ".ant-select-item-option-content span" });
    const optionRow = option.closest(".ant-select-item-option")!;
    expect(within(optionRow as HTMLElement).getByText("尚未登录")).toBeInTheDocument();
    expect(screen.queryByText("李四")).not.toBeInTheDocument();
    const memberOption = screen
      .getByText("chenning", { selector: ".ant-select-item-option-content span" })
      .closest(".ant-select-item-option")!;
    expect(within(memberOption as HTMLElement).getByText("已是成员")).toBeInTheDocument();
    expect(memberOption).toHaveClass("ant-select-item-option-disabled");
    fireEvent.click(option);

    const pick = await openRoleSelect("成员角色");
    const labels = Array.from(
      document.querySelectorAll(".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content"),
    ).map((el) => el.textContent);
    expect(labels).toEqual(["可查看", "可编辑", "管理员"]);
    fireEvent.click(await pick("可查看"));
    fireEvent.click(screen.getByRole("button", { name: "添加" }));

    await waitFor(() => {
      expect(api.addMember).toHaveBeenCalledWith("w1", { user_id: "u2", role: "viewer" });
    });
    expect(await screen.findByText("已添加成员 lisi")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("combobox", { name: "搜索已有用户" })).not.toBeInTheDocument(),
    );
    expect(openButton).toBeEnabled();
    expect(api.members).toHaveBeenCalledTimes(2);
  });

  it("添加栏提示用户不存在，取消后收起并清空", async () => {
    show();
    await screen.findByText("linxiao");
    fireEvent.click(screen.getByRole("button", { name: /添加成员/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "搜索已有用户" }), {
      target: { value: "nobody" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "用户不存在，请联系平台管理员在用户管理中创建",
    );
    expect(api.addMember).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("combobox", { name: "搜索已有用户" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /添加成员/ }));
    expect(screen.getByRole("combobox", { name: "搜索已有用户" })).toHaveValue("");
  });

  it("搜索失败时提示失败原因，不说用户不存在", async () => {
    vi.mocked(api.searchWorkspaceUsers).mockRejectedValue(new ApiError("服务暂不可用", 503, "UNAVAILABLE"));
    show();
    await screen.findByText("linxiao");
    fireEvent.click(screen.getByRole("button", { name: /添加成员/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "搜索已有用户" }), { target: { value: "lisi" } });
    expect(await screen.findByText("服务暂不可用")).toBeInTheDocument();
    expect(screen.queryByText("用户不存在，请联系平台管理员在用户管理中创建")).not.toBeInTheDocument();
  });

  it("下拉显示候选时回车不按半截输入添加，选中后回车添加所选用户", async () => {
    vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({
      items: [
        { id: "u4", username: "chen", display_name: "陈", last_login_at: null },
        { id: "u5", username: "chenxi", display_name: "陈曦", last_login_at: null },
      ],
    });
    vi.mocked(api.addMember).mockResolvedValue({
      id: 5, user_id: "u5", username: "chenxi", display_name: "陈曦", role: "member", last_login_at: null,
    });
    show();
    await screen.findByText("linxiao");
    fireEvent.click(screen.getByRole("button", { name: /添加成员/ }));
    const search = screen.getByRole("combobox", { name: "搜索已有用户" });
    fireEvent.change(search, { target: { value: "chen" } });
    const option = await screen.findByText("chenxi", { selector: ".ant-select-item-option-content span" });
    // Enter while suggestions are shown belongs to the dropdown: it must not add "chen" from the typed text.
    fireEvent.keyDown(search, { key: "Enter", code: "Enter", keyCode: 13, which: 13 });
    fireEvent.keyUp(search, { key: "Enter", code: "Enter", keyCode: 13, which: 13 });
    await new Promise((r) => setTimeout(r, 50));
    expect(api.addMember).not.toHaveBeenCalled();
    fireEvent.click(option);
    await waitFor(() => expect(search).toHaveValue("chenxi"));
    fireEvent.keyDown(search, { key: "Enter", code: "Enter", keyCode: 13, which: 13 });
    fireEvent.keyUp(search, { key: "Enter", code: "Enter", keyCode: 13, which: 13 });
    await waitFor(() => expect(api.addMember).toHaveBeenCalledWith("w1", { user_id: "u5", role: "member" }));
  });

  it("行内修改角色，LAST_ADMIN 错误浮动提示", async () => {
    vi.mocked(api.updateMemberRole).mockRejectedValueOnce(
      new ApiError("该空间至少需要一名管理员", 409, "LAST_ADMIN"),
    );
    vi.mocked(api.updateMemberRole).mockResolvedValueOnce(defaultMembers[1]);
    show();
    await screen.findByText("linxiao");

    let pick = await openRoleSelect("linxiao 角色");
    fireEvent.click(await pick("可编辑"));
    await waitFor(() => expect(api.updateMemberRole).toHaveBeenCalledWith("w1", 1, "member"));
    expect(await screen.findByText("该空间至少需要一名管理员")).toBeInTheDocument();

    pick = await openRoleSelect("chenning 角色");
    fireEvent.click(await pick("可查看"));
    await waitFor(() => expect(api.updateMemberRole).toHaveBeenCalledWith("w1", 2, "viewer"));
    expect(await screen.findByText("成员角色已更新")).toBeInTheDocument();
  });

  it("移除成员需 Popconfirm 确认", async () => {
    vi.mocked(api.removeMember).mockResolvedValue(undefined);
    show();
    await screen.findByText("chenning");

    fireEvent.click(screen.getByRole("button", { name: "移除 chenning" }));
    expect(api.removeMember).not.toHaveBeenCalled();
    const confirm = await screen.findByText("移除成员 chenning？");
    const popover = confirm.closest(".ant-popover") as HTMLElement;
    fireEvent.click(within(popover).getByRole("button", { name: "移除" }));

    await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith("w1", 2));
    expect(await screen.findByText("已移除成员")).toBeInTheDocument();
  });

  it("加载中显示骨架屏，失败后可重试", async () => {
    let fail!: (e: Error) => void;
    vi.mocked(api.members).mockReturnValueOnce(
      new Promise((_, reject) => {
        fail = reject;
      }),
    );
    const { container } = show();
    expect(container.querySelector(".ant-skeleton")).not.toBeNull();
    expect(screen.queryByText(/ 人$/)).not.toBeInTheDocument();

    fail(new Error("网络异常"));
    expect(await screen.findByText("网络异常")).toBeInTheDocument();
    // No member count and no adding against a list that failed to load.
    expect(screen.queryByText(/ 人$/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /添加成员/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("linxiao")).toBeInTheDocument();
    expect(api.members).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("网络异常")).not.toBeInTheDocument();
  });

  it("没有成员时显示空态", async () => {
    vi.mocked(api.members).mockResolvedValue({ items: [] });
    show();
    expect(await screen.findByText("暂无空间成员")).toBeInTheDocument();
    expect(screen.getByText("0 人")).toBeInTheDocument();
  });
});
