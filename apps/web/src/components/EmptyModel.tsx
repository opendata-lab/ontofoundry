import { Empty } from "antd";

export function EmptyModel({ text = "暂无构建结果" }: { text?: string }) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<strong className="text-ink-2">{text}</strong>} />;
}
