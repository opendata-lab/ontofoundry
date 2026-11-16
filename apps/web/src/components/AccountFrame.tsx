import { ArrowLeft, KeyRound, ScrollText, User as UserIcon, Users } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import type { User } from "../api/types";
import { Brand } from "./Brand";
import { UserMenu } from "./UserMenu";
import { ApplicationFrame, navLinkClass } from "./layout";

type AccountLink = { to: string; label: string; icon: ComponentType<{ className?: string }> };

const PERSONAL: AccountLink[] = [
  { to: "/me", label: "个人信息", icon: UserIcon },
  { to: "/me/tokens", label: "个人令牌", icon: KeyRound },
];
const PLATFORM: AccountLink[] = [
  { to: "/admin/users", label: "用户管理", icon: Users },
  { to: "/admin/audit", label: "用户审计", icon: ScrollText },
];

function AccountNavLink({ to, label, icon: Icon }: AccountLink) {
  return (
    <NavLink to={to} end className={({ isActive }) => navLinkClass(isActive)}>
      <Icon className="size-icon flex-none" />
      <span>{label}</span>
    </NavLink>
  );
}

function Group({ title, links }: { title: string; links: AccountLink[] }) {
  return (
    <div className="flex flex-col gap-1 border-t border-rule-soft pt-3" role="group" aria-label={title}>
      <h2 className="m-0 px-3 pb-1 text-xs font-medium text-muted">{title}</h2>
      {links.map((link) => <AccountNavLink key={link.to} {...link} />)}
    </div>
  );
}

/** Personal and platform-admin pages: the workspace frame with an account sidebar. */
export function AccountFrame({ user, children }: { user: User; children: ReactNode }) {
  return (
    <ApplicationFrame
      collapsed={false}
      header={
        <>
          <Link to="/" className="flex items-center gap-5 text-inherit">
            <Brand />
          </Link>
          <UserMenu user={user} />
        </>
      }
      sidebar={
        <nav aria-label="账号导航" className="flex flex-col gap-4">
          <Link to="/" className={navLinkClass(false)}>
            <ArrowLeft className="size-icon flex-none" />
            <span>返回工作空间</span>
          </Link>
          <Group title="个人" links={PERSONAL} />
          {user.is_platform_admin && <Group title="平台管理" links={PLATFORM} />}
        </nav>
      }
    >
      {children}
    </ApplicationFrame>
  );
}
