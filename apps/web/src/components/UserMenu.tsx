import { App, Avatar, Button, Dropdown } from "antd";
import type { MenuProps } from "antd";
import { ChevronDown, LogOut, ScrollText, User as UserIcon, Users } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { User } from "../api/types";

/** Header user dropdown shared across platform pages and workspace shell. */
export function UserMenu({ user }: { user: User }) {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = useCallback(async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await api.logout();
      navigate("/login", { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        navigate("/login", { replace: true });
        return;
      }
      void message.error(e instanceof Error ? e.message : "退出登录失败，请重试");
    } finally {
      setLoggingOut(false);
    }
  }, [loggingOut, message, navigate]);

  const items: MenuProps["items"] = [
    { key: "me", label: "个人中心", icon: <UserIcon className="size-icon-sm" /> },
    ...(user.is_platform_admin
      ? [
          { key: "admin-users", label: "用户管理", icon: <Users className="size-icon-sm" /> },
          { key: "admin-audit", label: "用户审计", icon: <ScrollText className="size-icon-sm" /> },
        ]
      : []),
    { type: "divider" },
    { key: "logout", label: "退出登录", icon: <LogOut className="size-icon-sm" /> },
  ];

  const initial = (user.display_name || user.username || "A").slice(0, 1).toUpperCase();

  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items,
        onClick: ({ key }) => {
          if (key === "me") navigate("/me");
          else if (key === "admin-users") navigate("/admin/users");
          else if (key === "admin-audit") navigate("/admin/audit");
          else if (key === "logout") void handleLogout();
        },
      }}
    >
      <Button
        type="text"
        aria-label={user.display_name || user.username || "用户菜单"}
        loading={loggingOut}
        className="flex items-center gap-2 px-2 text-xs text-inherit"
      >
        <Avatar className="size-6 bg-accent text-xs leading-6 text-accent-ink">
          {initial}
        </Avatar>
        <span>{user.display_name}</span>
        <ChevronDown className="size-icon" />
      </Button>
    </Dropdown>
  );
}
