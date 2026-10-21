import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { effectiveLinks } from "../../lib/coreModel";
import { shortObjectName } from "../../lib/objectMapping";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ObjectRelationGraph } from "./ObjectRelationGraph";

afterEach(cleanup);

function fixture() {
  const draft = example("06-inheritance");
  const type = draft.object_types.find((object) => object.name === "person")!;
  return { draft, type };
}

it("keeps the self relation label clear of radial relation labels", () => {
  const { draft, type } = fixture();
  const self = effectiveLinks(draft, type.id).find(({ definition }) => definition.source_type_id === definition.target_type_id)!.definition;
  renderWithProviders(<ObjectRelationGraph draft={draft} type={type} editing={false} canEdit={false} sessionId={null} change={vi.fn()} open={vi.fn()} />);
  const loop = screen.getByRole("group", { name: shortObjectName(self) });
  const label = within(loop).getByText(shortObjectName(self), { selector: "text" });
  const x = Number(label.getAttribute("x"));
  const y = Number(label.getAttribute("y"));
  for (const other of document.querySelectorAll("g[role=group] > text")) {
    if (other === label) continue;
    const distance = Math.hypot(x - Number(other.getAttribute("x")), y - Number(other.getAttribute("y")));
    expect(distance).toBeGreaterThan(40);
  }
  expect(document.querySelectorAll("circle")).toHaveLength(0);
});

it("labels a merged edge with an explicit relation count rather than cardinality", () => {
  const { draft, type } = fixture();
  const relation = effectiveLinks(draft, type.id).find(({ definition }) => definition.source_type_id !== definition.target_type_id)!.definition;
  draft.link_types.push({ ...relation, id: "00000000-0000-4000-8000-000000000099", name: "alternate_relation", display_name: "备用关系" });
  renderWithProviders(<ObjectRelationGraph draft={draft} type={type} editing={false} canEdit={false} sessionId={null} change={vi.fn()} open={vi.fn()} />);
  expect(screen.getByText("2 条关系", { selector: "text" })).toBeInTheDocument();
  const group = screen.getByRole("group", { name: `${shortObjectName(relation)}、备用关系` });
  expect(within(group).getByText(/备用关系/, { selector: "title" })).toBeInTheDocument();
});
