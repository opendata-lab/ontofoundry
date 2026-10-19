import { App } from "antd";
import { useEffect, useId, type ReactNode } from "react";

/** Keep recoverable operation errors out of the page layout. */
export function useErrorMessage(error: ReactNode) {
  const { message } = App.useApp();
  const key = useId();
  useEffect(() => {
    if (error) void message.error({ key, content: error, duration: 6 });
  }, [error, key, message]);
}
