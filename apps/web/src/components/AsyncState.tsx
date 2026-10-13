import { AlertCircle, RefreshCw } from "lucide-react";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

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

// Route-level fallback: without it React Router renders its developer page
// ("You can provide a way better UX…") whenever a page throws.
export function RouteErrorSurface() {
  const error = useRouteError();
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error);
  return (
    <div className="route-error">
      <div className="empty-state empty-state--error" role="alert">
        <AlertCircle size={24} aria-hidden="true" />
        <div>
          <strong>页面出错了</strong>
          <p>页面遇到意外错误，已停止显示。可以重新加载，或返回工作空间列表。</p>
          <p className="route-error__detail">{detail}</p>
        </div>
        <div className="route-error__actions">
          <button
            className="button button--secondary"
            onClick={() => window.location.reload()}
          >
            <RefreshCw size={16} aria-hidden="true" />
            重新加载
          </button>
          <a className="button button--secondary" href="/">
            返回工作空间列表
          </a>
        </div>
      </div>
    </div>
  );
}
