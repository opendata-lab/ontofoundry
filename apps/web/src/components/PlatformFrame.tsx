import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { User } from "../api/types";
import { Brand } from "./Brand";
import { UserMenu } from "./UserMenu";
import { DirectoryFrame } from "./layout";

/** Shared top-bar layout for directory, profile, and platform admin pages. */
export function PlatformFrame({ user, children }: { user: User; children: ReactNode }) {
  return (
    <DirectoryFrame
      header={
        <>
          <Link to="/" className="flex items-center gap-5 text-inherit">
            <Brand />
          </Link>
          <UserMenu user={user} />
        </>
      }
    >
      {children}
    </DirectoryFrame>
  );
}
