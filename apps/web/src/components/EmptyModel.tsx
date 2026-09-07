export function EmptyModel({ text = "暂无构建结果" }: { text?: string }) {
  return (
    <div className="empty-model">
      <div className="empty-model-art" aria-hidden="true">
        <i />
        <i />
        <i />
      </div>
      <strong>{text}</strong>
    </div>
  );
}
