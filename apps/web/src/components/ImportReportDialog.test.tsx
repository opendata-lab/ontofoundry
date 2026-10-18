import { act, cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { importApi, modelingApi } from "../api/client";
import type { ImportPreview } from "../api/types";
import { modelingSession } from "../test/apiRecords";
import { example } from "../test/drafts";
import { importPreview } from "../test/importRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { ImportReportDialog } from "./ImportReportDialog";

vi.mock("../api/client", async (load) => ({
  ...(await load<typeof import("../api/client")>()),
  importApi: { get: vi.fn() }, modelingApi: { get: vi.fn() },
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("removes the previous report while changing session and ignores its late response", async () => {
  const session = modelingSession({}, example("01-basic-sales"));
  vi.mocked(importApi.get).mockResolvedValue(importPreview);
  vi.mocked(modelingApi.get).mockResolvedValue(session);
  const props = { open: true, source: { adapter: "ossie-0.2", report_id: "fiction-import" }, session, onClose: vi.fn(), onChanged: vi.fn() };
  const { rerender } = renderWithProviders(<ImportReportDialog {...props} />);
  expect(await screen.findByText(/fiction.json · ossie-0.2/)).toBeInTheDocument();

  let finishOld!: (result: ImportPreview) => void;
  vi.mocked(importApi.get).mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
  rerender(<ImportReportDialog {...props} session={{ ...session, revision: session.revision + 1 }} />);
  let finishNew!: (result: ImportPreview) => void;
  vi.mocked(importApi.get).mockReturnValueOnce(new Promise((resolve) => { finishNew = resolve; }));
  const nextSession = { ...session, id: "other-fiction-session" };
  vi.mocked(modelingApi.get).mockResolvedValue(nextSession);
  rerender(<ImportReportDialog {...props} session={nextSession} source={{ ...props.source, report_id: "other-fiction-import" }} />);
  expect(screen.queryByText(/fiction.json · ossie-0.2/)).not.toBeInTheDocument();
  await act(async () => finishOld(importPreview));
  expect(screen.queryByText(/fiction.json · ossie-0.2/)).not.toBeInTheDocument();
  await act(async () => finishNew({ ...importPreview, filename: "other-fiction.json", import_id: "other-fiction-import" }));
  expect(await screen.findByText(/other-fiction.json · ossie-0.2/)).toBeInTheDocument();
});
