"use client";

import { Copy } from "lucide-react";
import { useId } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/** A one-time link in a read-only field with a copy button (select-all on focus as a fallback). */
export function CopyLink({ label, url }: { label: string; url: string }) {
  const t = useTranslations("admin");
  const common = useTranslations("common.actions");
  const toast = useToast();
  const id = useId();

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast(common("copied"), "ok");
    } catch {
      toast(t("copyFailed"), "bad");
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="flex gap-2">
        <Input id={id} readOnly value={url} className="font-mono" onFocus={(event) => event.target.select()} />
        <Button type="button" variant="primary" size="icon" aria-label={common("copy")} onClick={() => void copy()}>
          <Copy aria-hidden />
        </Button>
      </div>
    </div>
  );
}
