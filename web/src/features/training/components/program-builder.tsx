"use client";

import { CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import { GenerateForm } from "@/features/training/components/generate-form";
import { ProgramEditor } from "@/features/training/components/program-editor";
import { type DraftError, type DraftProgram, fromPreview, fromProgram, toProgramIn } from "@/features/training/program-draft";
import type { Exercise, ProgramList, ProgramOut, ProgramSummary } from "@/features/training/types";
import { bffGet } from "@/lib/bff-get";
import { post, put } from "@/lib/mutate";

/** What went wrong last: the draft's own checks, or the API's status. */
type Problem = { kind: "draft"; errors: DraftError[] } | { kind: "api"; status: number };

/** `/training/programs`: list, generate → preview → edit → save, activate (P6.6). */
export function ProgramBuilder({ initial, exercises }: { initial: ProgramSummary[]; exercises: Exercise[] }) {
  const t = useTranslations("training.programs");
  const states = useTranslations("common.states");
  const [programs, setPrograms] = useState(initial);
  const [draft, setDraft] = useState<DraftProgram | null>(null);
  const [minutes, setMinutes] = useState<number[] | null>(null);
  const [message, setMessage] = useState<{ text: string; programId?: number } | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    const result = await bffGet<ProgramList>("/v1/training/programs");
    if (result.ok && result.data) setPrograms(result.data.items);
  }

  async function edit(id: number) {
    setBusy(`edit-${id}`);
    setProblem(null);
    setMessage(null);
    const result = await bffGet<ProgramOut>(`/v1/training/programs/${id}`);
    setBusy(null);
    if (!result.ok || !result.data) return setProblem({ kind: "api", status: result.status });
    setDraft(fromProgram(result.data));
    setMinutes(null);
  }

  async function activate(id: number) {
    setBusy(`activate-${id}`);
    setProblem(null);
    const result = await post<ProgramOut>(`/v1/training/programs/${id}/activate`);
    setBusy(null);
    if (!result.ok) return setProblem({ kind: "api", status: result.status });
    setMessage({ text: t("activated") });
    await refresh();
  }

  async function save() {
    if (!draft) return;
    const checked = toProgramIn(draft);
    if (!checked.ok) return setProblem({ kind: "draft", errors: checked.errors });
    setBusy("save");
    setProblem(null);
    const result = draft.id
      ? await put<ProgramOut>(`/v1/training/programs/${draft.id}`, checked.body)
      : await post<ProgramOut>("/v1/training/programs", checked.body);
    setBusy(null);
    if (!result.ok || !result.data) return setProblem({ kind: "api", status: result.status });
    setDraft(null);
    setMinutes(null);
    setMessage({ text: t("saved", { name: result.data.name }), programId: result.data.active ? undefined : result.data.id });
    await refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {message ? (
        <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-card border border-ok/30 bg-ok-soft p-4 text-sm font-medium text-ok">
          <span className="inline-flex items-center gap-2">
            <CheckCircle2 aria-hidden className="size-5" />
            {message.text}
          </span>
          {message.programId ? (
            <Button onClick={() => void activate(message.programId as number)} disabled={busy !== null}>
              {t("activateIt")}
            </Button>
          ) : null}
        </div>
      ) : null}
      {problem ? (
        <Failure
          title={t("failed")}
          message={
            problem.kind === "draft" ? (
              <ul className="list-disc pl-4">
                {problem.errors.map((e, i) => (
                  <li key={i}>{t(`errors.${e.key}`, { day: e.day ?? 0, name: e.name ?? "" })}</li>
                ))}
              </ul>
            ) : isBackendDown(problem.status) ? (
              states("backendDown")
            ) : (
              t("refused")
            )
          }
        />
      ) : null}

      <ProgramList programs={programs} busy={busy !== null} onEdit={(id) => void edit(id)} onActivate={(id) => void activate(id)} />

      {draft ? (
        <ProgramEditor
          draft={draft}
          minutes={minutes}
          exercises={exercises}
          onChange={setDraft}
          onSave={() => void save()}
          onCancel={() => {
            setDraft(null);
            setMinutes(null);
          }}
          saving={busy === "save"}
        />
      ) : (
        <GenerateForm
          onPreview={(preview) => {
            setDraft(fromPreview(preview));
            setMinutes(preview.days.map((d) => d.estimated_minutes));
            setMessage(null);
            setProblem(null);
          }}
        />
      )}
    </div>
  );
}

function ProgramList({
  programs,
  busy,
  onEdit,
  onActivate,
}: {
  programs: ProgramSummary[];
  busy: boolean;
  onEdit: (id: number) => void;
  onActivate: (id: number) => void;
}) {
  const t = useTranslations("training.programs");
  const goals = useTranslations("training.goals");
  return (
    <Card aria-labelledby="programs-title">
      <CardHeader>
        <CardTitle id="programs-title">{t("yours")}</CardTitle>
      </CardHeader>
      {programs.length === 0 ? (
        <Empty title={t("empty")}>{t("emptyHint")}</Empty>
      ) : (
        <ul className="divide-y divide-border" data-testid="program-list">
          {programs.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3" data-program-id={p.id}>
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 font-semibold">
                  {p.name} {p.active ? <Badge tone="ok">{t("active")}</Badge> : null}
                </p>
                <p className="text-sm text-muted">{t("meta", { goal: goals(p.goal), days: p.days_per_week, weeks: p.weeks })}</p>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => onEdit(p.id)} disabled={busy} aria-label={t("editLabel", { name: p.name })}>
                  {t("edit")}
                </Button>
                {p.active ? null : (
                  <Button onClick={() => onActivate(p.id)} disabled={busy} aria-label={t("activateLabel", { name: p.name })}>
                    {t("activate")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
