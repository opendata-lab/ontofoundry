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
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("preserves inherited counts, session detail links and search in the object table", () => {
  renderWithProviders(
    <MemoryRouter initialEntries={["/objects?session=session-demo"]}>
      <TypeCatalogPage kind="object_type" />
    </MemoryRouter>,
  );
  const person = screen.getByRole("link", { name: "个人" });
  const row = within(person.closest("tr")!);
  const cells = row.getAllByRole("cell");
  expect(cells[1]).toHaveTextContent("person");
  expect(cells[2]).toHaveTextContent("当事人");
  expect(cells[4]).toHaveTextContent("6");
  expect(cells[7]).toHaveTextContent("1");
  expect(person.getAttribute("href")).toContain("/elements/object_type/");
  expect(person.getAttribute("href")).toContain("session=session-demo");
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "person" } });
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "个人" })).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "不存在的对象" } });
  expect(screen.getByText("没有匹配的定义")).toBeInTheDocument();
});

it("shows a relation's identifier, meaning, multiplicity and the basic detail tab", () => {
  renderWithProviders(
    <MemoryRouter initialEntries={["/relations?session=session-demo"]}>
      <TypeCatalogPage kind="link_type" />
    </MemoryRouter>,
  );
  const link = screen.getByRole("link", { name: "signer" });
  const row = within(link.closest("tr")!);
  expect(row.getAllByRole("cell")[1]).toHaveTextContent("signer");
  expect(row.getAllByRole("cell")[2]).toHaveTextContent(/合同.*当事人/);
  expect(row.getByText("多对一")).toBeInTheDocument();
  expect(link.getAttribute("href")).toContain("/elements/link_type/");
  expect(link.getAttribute("href")).toContain("tab=basic");
});


it("searches the optional Chinese relation name and keeps its English identifier", async () => {
  const snapshotModule = await import("../hooks/useSnapshot");
  const draft = example("06-inheritance");
  draft.link_types.find((link) => link.name === "signer")!.display_name = "签约方";
  vi.spyOn(snapshotModule, "useSnapshot").mockReturnValue({ ...snapshotModule.useSnapshot(workspace()), draft });
  renderWithProviders(<MemoryRouter initialEntries={["/?session=session-demo"]}><TypeCatalogPage kind="link_type" /></MemoryRouter>);
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "签约方" } });
  const link = screen.getByRole("link", { name: "签约方" });
  expect(within(link.closest("tr")!).getByText("signer")).toBeInTheDocument();
});
