import { AlertCircle, RefreshCw } from "lucide-react";

export function LoadingSurface({ label = "正在读取…" }: { label?: string }) {
  return (
    <div className="loading-surface" role="status" aria-live="polite">
      <div className="skeleton skeleton--short" />
      <div className="skeleton" />
      <div className="skeleton skeleton--medium" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function ErrorSurface({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="empty-state empty-state--error" role="alert">
      <AlertCircle size={24} aria-hidden="true" />
      <div>
        <strong>数据没有加载完成</strong>
        <p>{message}。请检查 API 服务后重试。</p>
      </div>
      {retry && (
        <button className="button button--secondary" onClick={retry}>
          <RefreshCw size={16} aria-hidden="true" />
          重新加载
        </button>
      )}
    </div>
  );
}
