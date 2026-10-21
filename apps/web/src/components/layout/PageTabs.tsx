import { Tabs, type TabsProps } from "antd";
import type { ReactNode } from "react";
import { PageHeader } from "../PageHeader";

/** Page categories share the white title band and retain Ant Design panels. */
export function PageTabs({ title, note, actions, ...tabs }: {
  title: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
} & Pick<TabsProps, "activeKey" | "onChange" | "items">) {
  return (
    <Tabs
      {...tabs}
      className="page-tabs min-h-0 flex-1"
      renderTabBar={(props, DefaultTabBar) => (
        <PageHeader title={title} note={note} tabBar={<DefaultTabBar {...props} className="mb-0 px-4 before:border-0" />}>
          {actions}
        </PageHeader>
      )}
    />
  );
}
