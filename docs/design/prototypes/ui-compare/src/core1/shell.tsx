import "@ant-design/v5-patch-for-react-19";
import "../antd/antd.css";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import { StyleProvider } from "@ant-design/cssinjs";
import zhCN from "antd/locale/zh_CN";

const PAGES = [
  { href: "/core1-metric.html", label: "① 新建指标" },
  { href: "/core1-derived.html", label: "② 子对象派生条件" },
  { href: "/core1-import.html", label: "③ 导入" },
];

function Shell({ children }: { children: ReactNode }) {
  const here = location.pathname;
  return (
    <div className="min-h-screen">
      <nav className="flex items-center gap-1 border-b border-rule bg-surface px-6 py-2 text-sm">
        <span className="mr-4 font-semibold text-ink">core-1 交互原型</span>
        {PAGES.map((p) => (
          <a key={p.href} href={p.href}
            className={`rounded-sm px-3 py-1.5 no-underline ${here === p.href ? "bg-accent-soft font-medium text-accent" : "text-ink-2 hover:bg-surface-soft"}`}>
            {p.label}
          </a>
        ))}
        <span className="ml-auto text-xs text-muted">虚构数据 · 不连接后端</span>
      </nav>
      {children}
    </div>
  );
}

export function mount(node: ReactNode) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <StyleProvider layer>
        <ConfigProvider
          locale={zhCN}
          theme={{
            token: {
              colorPrimary: "#0061ef",
              colorText: "#20252d",
              colorTextSecondary: "#67717e",
              colorBorder: "#e3e9f1",
              colorBorderSecondary: "#edf1f6",
              colorBgLayout: "#f5f7fb",
              borderRadius: 6,
              fontFamily: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
            },
          }}
        >
          <AntApp>
            <Shell>{node}</Shell>
          </AntApp>
        </ConfigProvider>
      </StyleProvider>
    </StrictMode>,
  );
}
