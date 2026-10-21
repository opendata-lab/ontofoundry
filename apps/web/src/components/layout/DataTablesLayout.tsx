import type { ReactNode } from "react";
import { Panel } from "./Panel";

/** A responsive operations sidebar and registered table list. */
export function DataTablesLayout({ controls, children }: { controls: ReactNode; children: ReactNode }) {
  return <div className="data-tables-layout"><Panel><aside aria-label="数据表操作区" className="flex flex-col gap-4 p-4">{controls}</aside></Panel><Panel><div className="min-w-0 overflow-auto">{children}</div></Panel></div>;
}
