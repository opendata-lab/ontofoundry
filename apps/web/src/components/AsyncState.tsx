import { Alert, Button, Result, Skeleton } from "antd";
import { RefreshCw } from "lucide-react";
import { AsyncSurface } from "./layout";
import { isRouteErrorResponse, useRouteError } from "react-router-dom";

export function LoadingSurface({ label = "正在读取…" }: { label?: string }) {
  return (
    <AsyncSurface role="status" aria-live="polite" aria-label={label}>
      <Skeleton active paragraph={{ rows: 3 }} />
      <span className="sr-only">{label}</span>
    </AsyncSurface>
  );
}

export function ErrorSurface({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <AsyncSurface>
      <Alert
        type="error"
        showIcon
        role="alert"
        message="数据没有加载完成"
        description={`${message}。请检查 API 服务后重试。`}
        action={
          retry && (
            <Button size="small" icon={<RefreshCw className="size-icon-sm" />} onClick={retry}>
              重新加载
            </Button>
          )
        }
      />
    </AsyncSurface>
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
    <AsyncSurface fullPage role="alert">
      <Result
        status="error"
        title="页面出错了"
        subTitle={
          <>
            页面遇到意外错误，已停止显示。可以重新加载，或返回工作空间列表。
            <code className="mt-2 block text-xs">{detail}</code>
          </>
        }
        extra={[
          <Button key="reload" icon={<RefreshCw className="size-icon-sm" />} onClick={() => window.location.reload()}>
            重新加载
          </Button>,
          <Button key="home" href="/">
            返回工作空间列表
          </Button>,
        ]}
      />
    </AsyncSurface>
  );
}
