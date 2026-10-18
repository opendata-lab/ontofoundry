import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { importPreview } from "../test/importRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { TranslationReport } from "./TranslationReport";
afterEach(cleanup);
it("filters results and expands original text, real lines and matched target ids", async () => {
  renderWithProviders(<TranslationReport report={importPreview.report} idMap={importPreview.id_map} />);
  fireEvent.click(screen.getAllByRole("button", { name: "展开行" })[0]);
  expect(await screen.findByText("格式化材料第 4–12 行")).toBeInTheDocument();
  expect(screen.getByText("workspace-order")).toBeInTheDocument();
  expect(screen.getByText(importPreview.report.issues[0].original!)).toBeInTheDocument();
  fireEvent.click(screen.getByText("需处理 1"));
  expect(screen.queryByText("保留业务对象定义")).not.toBeInTheDocument();
  expect(screen.getByText(importPreview.report.issues[1].message)).toBeInTheDocument();
});
