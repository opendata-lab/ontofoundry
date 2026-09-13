import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders GFM while removing executable markup", () => {
    const { container } = render(
      <Markdown>{"# 标题\n\n|列|值|\n|-|-|\n|A|1|\n\n<script>alert(1)</script>"}</Markdown>,
    );
    expect(screen.getByRole("heading", { name: "标题" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });
});
