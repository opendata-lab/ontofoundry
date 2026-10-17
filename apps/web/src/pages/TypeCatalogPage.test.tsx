import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { example } from "../test/drafts";
import { workspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { TypeCatalogPage } from "./TypeCatalogPage";

vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace: workspace() }) }));
vi.mock("../hooks/useSnapshot", () => ({
  useSnapshot: () => ({
    draft: example("06-inheritance"),
    sessionId: "session-demo",
    suffix: "?session=session-demo",
    load: vi.fn(),
  }),
}));
afterEach(cleanup);

it("preserves inherited counts, session detail links and search in the object table", () => {
  renderWithProviders(
    <MemoryRouter initialEntries={["/objects?session=session-demo"]}>
      <TypeCatalogPage kind="object_type" />
    </MemoryRouter>,
  );
  const person = screen.getByRole("link", { name: "个人" });
  const row = within(person.closest("tr")!);
  expect(row.getByText("继承 当事人")).toBeInTheDocument();
  expect(row.getAllByRole("cell")[1]).toHaveTextContent("6");
  expect(row.getAllByRole("cell")[4]).toHaveTextContent("1");
  expect(person.getAttribute("href")).toContain("inspectSession=session-demo");
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "person" } });
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "个人" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "不存在的对象" } });
  expect(screen.getByText("没有匹配的本体模型")).toBeInTheDocument();
});

it("keeps relation endpoints, multiplicity and the basic detail tab", () => {
  renderWithProviders(
    <MemoryRouter initialEntries={["/relations"]}>
      <TypeCatalogPage kind="link_type" />
    </MemoryRouter>,
  );
  const link = screen.getByRole("link", { name: "签约方" });
  const row = within(link.closest("tr")!);
  expect(row.getByText("合同")).toBeInTheDocument();
  expect(row.getByText("当事人")).toBeInTheDocument();
  expect(row.getByText("多对一")).toBeInTheDocument();
  expect(link.getAttribute("href")).toContain("inspectTab=basic");
});
