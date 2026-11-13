import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { FeedbackItem, User, Workspace } from "../api/types";
import { workspace as makeWorkspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { FeedbackPage } from "./FeedbackPage";

const context = vi.hoisted(() => ({
  workspace: {} as Workspace,
  user: {} as User,
  refresh: vi.fn(),
}));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => context,
}));
vi.mock("../hooks/usePageTab", () => ({
  usePageTab: vi.fn(),
  usePageActive: () => true,
}));
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      feedback: vi.fn(),
    },
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

const page1Items: FeedbackItem[] = [
  {
    id: "fb-1",
    created_at: "2026-11-13T08:00:00Z",
    user: { id: "u2", display_name: "王五" },
    kind: "correction",
    user_text: "净销售额应该再扣掉运费，你算的不对",
    agent_text: "回答采用指标净销售额（v13），用户认为需扣减运费",
    elements: [
      { id: "el-1", name: "net_sales", display_name: "净销售额" },
      { id: "el-2", name: "freight_fee", display_name: null },
      { id: "el-gone" },
    ],
    version_number: 13,
  },
  {
    id: "fb-2",
    created_at: "2026-11-12T10:20:00Z",
    user: { id: "u3", display_name: "李四" },
    kind: "suggestion",
    user_text: "建议给星舟订单补充渠道来源属性",
    agent_text: "当前订单实体暂无渠道字段",
    elements: [],
    version_number: null,
  },
];

const page2Items: FeedbackItem[] = [
  {
    id: "fb-3",
    created_at: "2026-11-11T09:00:00Z",
    user: { id: "u4", display_name: "赵六" },
    kind: "suggestion",
    user_text: "补充含税与不含税口径区分",
    agent_text: "指标未标注是否含税",
    elements: [{ id: "el-3", name: "gross_amount", display_name: "采购总额" }],
    version_number: 12,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  context.user = adminUser;
  context.workspace = makeWorkspace({
    id: "ws-starport",
    slug: "starport-sales",
    name: "星港销售空间",
    role: "admin",
  });
  vi.mocked(api.feedback).mockResolvedValue({
    items: page1Items,
    next_cursor: null,
  });
});

afterEach(cleanup);

function show() {
  return renderWithProviders(
    <MemoryRouter>
      <FeedbackPage />
    </MemoryRouter>,
  );
}

describe("用户反馈页", () => {
  it("非空间管理员与非平台管理员显示 403 无权访问且不发起请求", () => {
    for (const ws of [
      makeWorkspace({ role: "member" }),
      makeWorkspace({ role: "viewer" }),
      makeWorkspace({ role: null, is_public: true, visibility: "public" }),
    ]) {
      context.workspace = ws;
      show();
      expect(screen.getByText("无权访问")).toBeInTheDocument();
      expect(
        screen.getByText("只有该工作空间的管理员或平台管理员可以查看「用户反馈」。"),
      ).toBeInTheDocument();
      cleanup();
    }
    expect(api.feedback).not.toHaveBeenCalled();
  });

  it("展示反馈列表、类型标签、元素名称降级及版本号，并支持游标加载更多", async () => {
    vi.mocked(api.feedback)
      .mockResolvedValueOnce({ items: page1Items, next_cursor: "cursor-2" })
      .mockResolvedValueOnce({ items: page2Items, next_cursor: null });

    show();

    expect(screen.getByRole("heading", { name: "用户反馈" })).toBeInTheDocument();
    await waitFor(() => {
      expect(api.feedback).toHaveBeenCalledWith("ws-starport", { limit: 20 });
    });

    const row1 = (await screen.findByText("净销售额应该再扣掉运费，你算的不对")).closest("tr")!;
    expect(within(row1).getByText("王五")).toBeInTheDocument();
    expect(within(row1).getByText("纠正")).toBeInTheDocument();
    expect(within(row1).getByText("回答采用指标净销售额（v13），用户认为需扣减运费")).toBeInTheDocument();
    expect(within(row1).getByText("净销售额")).toBeInTheDocument();
    expect(within(row1).getByText("freight_fee")).toBeInTheDocument();
    expect(within(row1).getByText("el-gone")).toBeInTheDocument();
    expect(within(row1).getByText("v13")).toBeInTheDocument();

    const row2 = screen.getByText("建议给星舟订单补充渠道来源属性").closest("tr")!;
    expect(within(row2).getByText("建议")).toBeInTheDocument();
    expect(within(row2).getByText("—")).toBeInTheDocument();
    expect(within(row2).getByText("未发布")).toBeInTheDocument();

    const loadMoreBtn = screen.getByRole("button", { name: "加载更多" });
    fireEvent.click(loadMoreBtn);

    await waitFor(() => {
      expect(api.feedback).toHaveBeenCalledWith("ws-starport", {
        cursor: "cursor-2",
        limit: 20,
      });
    });
    expect(await screen.findByText("补充含税与不含税口径区分")).toBeInTheDocument();
    expect(screen.getByText("净销售额应该再扣掉运费，你算的不对")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
  });

  it("接口返回 403 时展示无权限结果", async () => {
    vi.mocked(api.feedback).mockRejectedValueOnce(new ApiError("无权限", 403));
    show();
    expect(await screen.findByText("无权访问")).toBeInTheDocument();
  });

  it("平台管理员即使非空间显式成员也可查看反馈列表", async () => {
    context.user = { ...adminUser, is_platform_admin: true };
    context.workspace = makeWorkspace({
      id: "ws-starport",
      role: null,
      is_public: false,
    });
    show();
    expect(await screen.findByText("净销售额应该再扣掉运费，你算的不对")).toBeInTheDocument();
  });
});
