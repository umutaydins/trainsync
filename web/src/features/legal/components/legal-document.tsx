import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { LEGAL_SECTIONS, LEGAL_UPDATED, type LegalDoc } from "@/features/legal/content";

/** The privacy or terms text: numbered sections, the contact address as a mail link. */
export function LegalDocument({ doc, email }: { doc: LegalDoc; email: string }) {
  const t = useTranslations(`legal.${doc}.sections`);
  const legal = useTranslations("legal");
  const format = useFormatter();
  const updated = format.dateTime(new Date(`${LEGAL_UPDATED}T12:00:00Z`), { dateStyle: "long" });
  const mail = (chunks: ReactNode) => (
    <a href={`mailto:${email}`} className="font-semibold text-accent-ink underline underline-offset-4">
      {chunks}
    </a>
  );
  return (
    <article className="flex flex-col gap-8">
      <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
        {legal("updated", { date: updated })}
      </p>
      {LEGAL_SECTIONS[doc].map((section, index) => (
        <section key={section.id} aria-labelledby={`${doc}-${section.id}`} className="flex flex-col gap-3">
          <h2 id={`${doc}-${section.id}`} className="flex items-baseline gap-3 text-xl font-bold tracking-tight">
            <span aria-hidden className="font-mono text-sm text-accent-ink tabular">
              {String(index + 1).padStart(2, "0")}
            </span>
            {t(`${section.id}.title`)}
          </h2>
          {section.paragraphs.map((key, position) => (
            <div key={key} className="flex flex-col gap-3">
              <p className="leading-relaxed text-muted">
                {t.rich(`${section.id}.${key}`, { email, link: mail })}
              </p>
              {position === 0 && section.items ? (
                <ul className="flex flex-col gap-2 border-l-2 border-accent pl-4">
                  {section.items.map((item) => (
                    <li key={item} className="leading-relaxed">
                      {t(`${section.id}.items.${item}`)}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </section>
      ))}
    </article>
  );
}
