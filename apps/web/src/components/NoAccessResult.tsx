import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";
import { PageBody } from "./layout";

/** Standard 403 surface for restricted platform and workspace routes. */
export function NoAccessResult({
  title = "无权访问",
  subtitle,
  actionLabel = "返回工作空间目录",
  onBack,
}: {
  title?: string;
  subtitle: string;
  actionLabel?: string;
  onBack?: () => void;
}) {
  const navigate = useNavigate();
  return (
    <PageBody>
      <div className="flex flex-1 items-center justify-center">
        <Result
          status="403"
          title={title}
          subTitle={subtitle}
          extra={
            <Button type="primary" onClick={onBack ?? (() => navigate("/"))}>
              {actionLabel}
            </Button>
          }
        />
      </div>
    </PageBody>
  );
}
