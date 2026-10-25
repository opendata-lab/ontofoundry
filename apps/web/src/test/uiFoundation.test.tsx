import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Button, DatePicker, Modal, Select, Table } from "antd";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { antdTheme } from "../theme/antdTheme";
import { renderWithProviders } from "./renderWithProviders";

afterEach(async () => {
  cleanup();
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
});

describe("antd theme from tokens", () => {
  const tokens: Record<string, string> = {
    "--color-accent": "#0061ef",
    "--color-success": "oklch(43% 0.128 151)",
    "--font-body": '"PingFang SC", sans-serif',
    "--text-sm": "14px",
    "--radius-sm": "6px",
    "--control-height": "32px",
  };
  const theme = antdTheme((name) => tokens[name] ?? "");

  it("maps hex colours, fonts and pixel radii", () => {
    expect(theme.token).toMatchObject({
      colorPrimary: "#0061ef",
      fontFamily: '"PingFang SC", sans-serif',
      borderRadius: 6,
    });
  });

  it("keeps the workbench compact with 14px text and small-radius buttons", () => {
    expect(theme.token?.fontSize).toBe(14);
    expect(theme.components?.Button).toMatchObject({ borderRadius: 6, controlHeight: 32 });
  });

  it("leaves out colours Ant Design cannot parse and tokens that are unset", () => {
    expect(theme.token).not.toHaveProperty("colorSuccess");
    expect(theme.token).not.toHaveProperty("colorText");
  });
});

describe("Ant Design inside the app providers", () => {
  it("uses the Chinese locale", () => {
    renderWithProviders(
      <>
        <DatePicker />
        <Table dataSource={[]} columns={[{ title: "名称", dataIndex: "name" }]} />
      </>,
    );
    expect(screen.getByPlaceholderText("请选择日期")).toBeInTheDocument();
    expect(screen.getAllByText("暂无数据").length).toBeGreaterThan(0);
  });

  it("selects an option from a searchable Select with the keyboard", async () => {
    function Picker() {
      const [value, setValue] = useState<string>();
      return (
        <>
          <Select
            aria-label="数据集"
            showSearch
            optionFilterProp="label"
            value={value}
            onChange={setValue}
            options={[
              { value: "orders", label: "订单 orders" },
              { value: "stores", label: "门店 stores" },
            ]}
          />
          <output>{value ?? "未选择"}</output>
        </>
      );
    }
    renderWithProviders(<Picker />);
    const input = screen.getByRole("combobox", { name: "数据集" });
    fireEvent.mouseDown(input);
    fireEvent.change(input, { target: { value: "门店" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("stores"));
  });

  it("opens and closes a Modal", async () => {
    function Dialog() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <Button onClick={() => setOpen(true)}>新建指标</Button>
          <Modal title="指标表单" open={open} onCancel={() => setOpen(false)} footer={null}>
            表单内容
          </Modal>
        </>
      );
    }
    renderWithProviders(<Dialog />);
    fireEvent.click(screen.getByRole("button", { name: "新建指标" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("表单内容")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByText("表单内容")).not.toBeVisible());
  });
});
