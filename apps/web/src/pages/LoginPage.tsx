import { Alert, Button, Divider, Form, Input } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, navigation } from "../api/client";
import type { AuthOptions, LocalLoginRequest } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { Brand } from "../components/Brand";
import { Panel } from "../components/layout";

/** Keep post-login redirects on same-origin app paths and avoid bouncing back to /login. */
function safeReturnTo(value: string | null): string {
  if (!value) return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/";
  if (Array.from(value).some((char) => char.charCodeAt(0) < 32)) return "/";
  if (value === "/login" || value.startsWith("/login?") || value.startsWith("/login#")) return "/";
  return value;
}

/** Error codes the backend appends to /login when an SSO callback fails. */
const OAUTH_ERRORS: Record<string, string> = {
  oauth_denied: "认证服务未授权登录，请重试",
  oauth_exchange_failed: "认证服务令牌交换失败，请重新登录",
  oauth_user_info_failed: "认证服务用户信息获取失败，请重新登录",
};

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = safeReturnTo(searchParams.get("return_to"));
  const oauthError = OAUTH_ERRORS[searchParams.get("error") ?? ""] ?? "";
  const [form] = Form.useForm<LocalLoginRequest>();
  const [options, setOptions] = useState<AuthOptions | null>(null);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setLoadError("");
    api
      .authOptions()
      .then((data) => {
        if (seq === requestSeq.current) setOptions(data);
      })
      .catch((error: Error) => {
        if (seq === requestSeq.current) setLoadError(error.message);
      });
  }, []);

  useEffect(() => {
    load();
    return () => {
      requestSeq.current += 1;
    };
  }, [load]);

  const handleLocalLogin = async (values: LocalLoginRequest) => {
    setSubmitting(true);
    setSubmitError("");
    try {
      await api.loginLocal(values);
      navigate(returnTo, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSubmitError("用户名或密码错误");
      } else {
        setSubmitError(error instanceof Error ? error.message : "登录失败，请重试");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loadError) return <ErrorSurface message={loadError} retry={load} />;
  if (!options) return <LoadingSurface label="正在加载登录方式…" />;

  const { local_login: localLogin, oauth } = options;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas p-6">
      <Panel className="w-full max-w-sm p-6">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <h1 className="m-0 flex items-center justify-center">
            <Brand />
          </h1>
          <p className="m-0 text-xs text-muted">请登录后继续</p>
        </div>

        {oauthError && (
          <Alert type="error" showIcon role="alert" className="mb-4" message={oauthError} />
        )}

        {localLogin && (
          <Form<LocalLoginRequest>
            form={form}
            layout="vertical"
            requiredMark={false}
            onValuesChange={() => {
              if (submitError) setSubmitError("");
            }}
            onFinish={(values) => void handleLocalLogin(values)}
          >
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, whitespace: true, message: "请输入用户名" }]}
            >
              <Input aria-label="用户名" autoComplete="username" autoFocus />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: "请输入密码" }]}
            >
              <Input.Password aria-label="密码" autoComplete="current-password" />
            </Form.Item>
            {submitError && (
              <Alert
                type="error"
                showIcon
                role="alert"
                className="mb-4"
                message={submitError}
              />
            )}
            <Form.Item className="mb-0">
              <Button type="primary" htmlType="submit" block loading={submitting}>
                登录
              </Button>
            </Form.Item>
          </Form>
        )}

        {localLogin && oauth && (
          <Divider plain className="my-4">
            <span className="text-xs text-muted">或</span>
          </Divider>
        )}

        {oauth && (
          <Button
            type={localLogin ? "default" : "primary"}
            block
            onClick={() => navigation.assign(api.oauthLoginUrl(oauth.name, returnTo))}
          >
            {`通过 ${oauth.name} 登录`}
          </Button>
        )}

        {!localLogin && !oauth && (
          <Alert
            type="warning"
            showIcon
            role="alert"
            message="当前未启用任何登录方式，请联系管理员检查配置。"
          />
        )}
      </Panel>
    </main>
  );
}
