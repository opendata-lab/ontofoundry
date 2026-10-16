import { StyleProvider } from "@ant-design/cssinjs";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import dayjs from "dayjs";
import "dayjs/locale/zh-cn";
import { useMemo, type ReactNode } from "react";
import { antdTheme } from "./antdTheme";

dayjs.locale("zh-cn");

/**
 * Ant Design root: styles go into the `antd` cascade layer declared in
 * styles/index.css, Chinese locale, and the theme read from tokens.css.
 * Components call App.useApp() for message/modal/notification so those
 * follow this theme and locale.
 */
export function UiProvider({ children }: { children: ReactNode }) {
  const theme = useMemo(() => antdTheme(), []);
  return (
    <StyleProvider layer>
      <ConfigProvider locale={zhCN} theme={theme}>
        <AntApp component={false}>{children}</AntApp>
      </ConfigProvider>
    </StyleProvider>
  );
}
