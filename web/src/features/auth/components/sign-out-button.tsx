import { LogOut } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button, type ButtonProps } from "@/components/ui/button";

/**
 * Sign out: a plain form post to `/api/auth/logout` (works without JavaScript), which revokes the
 * API session, clears the cookies and goes to the sign-in page.
 */
export function SignOutButton({
  variant = "outline",
  size = "md",
  block = false,
  className,
}: Pick<ButtonProps, "variant" | "size" | "block" | "className">) {
  const t = useTranslations("common.actions");
  return (
    <form method="post" action="/api/auth/logout" className={block ? "w-full" : undefined}>
      <Button type="submit" variant={variant} size={size} block={block} className={className}>
        <LogOut aria-hidden />
        {t("signOut")}
      </Button>
    </form>
  );
}
