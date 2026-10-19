"use client";

import { useId, useState } from "react";

import { ExercisePicker } from "@/features/training/components/exercise-picker";
import { Badge, Card, EmptyState, ErrorState, buttonClass, inputClass, secondaryButtonClass } from "@/components/ui";
import { bffGet } from "@/lib/bff-get";
import { post, put } from "@/lib/mutate";
import {
  type DraftDay,
  type DraftExercise,
  type DraftProgram,
  fromPreview,
  fromProgram,
  move,
  newExercise,
  toProgramIn,
} from "@/features/training/program-draft";
import type {
  Equipment,
  Exercise,
  GenerateIn,
  ProgramGoal,
  ProgramList,
  ProgramOut,
  ProgramPreview,
  ProgramSummary,
} from "@/features/training/types";
import { EQUIPMENT, GOALS, label } from "@/features/training/types";

const DAY_OPTIONS = [2, 3, 4, 6] as const;

/** `/training/programs`: list, generate → preview → edit → save, activate (P6.6). */
export function ProgramBuilder({ initial, exercises }: { initial: ProgramSummary[]; exercises: Exercise[] }) {
  const [programs, setPrograms] = useState(initial);
  const [draft, setDraft] = useState<DraftProgram | null>(null);
  const [minutes, setMinutes] = useState<number[] | null>(null);
  const [message, setMessage] = useState<{ text: string; programId?: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    const result = await bffGet<ProgramList>("/v1/training/programs");
    if (result.ok && result.data) setPrograms(result.data.items);
  }

  async function edit(id: number) {
    setBusy(`edit-${id}`);
    setError(null);
    setMessage(null);
    const result = await bffGet<ProgramOut>(`/v1/training/programs/${id}`);
    setBusy(null);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : result.error);
    setDraft(fromProgram(result.data));
    setMinutes(null);
  }

  async function activate(id: number) {
    setBusy(`activate-${id}`);
    setError(null);
    const result = await post<ProgramOut>(`/v1/training/programs/${id}/activate`);
    setBusy(null);
    if (!result.ok) return setError(result.error);
    setMessage({ text: "Program activated. Start a day from Today." });
    await refresh();
  }

  async function save() {
    if (!draft) return;
    const checked = toProgramIn(draft);
    if (!checked.ok) return setError(checked.errors.join(". "));
    setBusy("save");
    setError(null);
    const result = draft.id
      ? await put<ProgramOut>(`/v1/training/programs/${draft.id}`, checked.body)
      : await post<ProgramOut>("/v1/training/programs", checked.body);
    setBusy(null);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : detailText(result.error, result.detail));
    setDraft(null);
    setMinutes(null);
    setMessage({ text: `Saved “${result.data.name}”.`, programId: result.data.active ? undefined : result.data.id });
    await refresh();
  }

  return (
    <div className="space-y-4">
      {message ? (
        <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-ok/30 bg-ok-soft px-4 py-3 text-sm text-ok">
          <span>{message.text}</span>
          {message.programId ? (
            <button type="button" className={`${buttonClass} min-h-11`} onClick={() => void activate(message.programId as number)} disabled={busy !== null}>
              Activate it
            </button>
          ) : null}
        </div>
      ) : null}
      {error ? <ErrorState title="That did not work" message={error} /> : null}

      <Card title="Your programs" labelledBy="programs-title">
        {programs.length === 0 ? (
          <EmptyState title="No programs yet">Generate one below.</EmptyState>
        ) : (
          <ul className="divide-y divide-border" data-testid="program-list">
            {programs.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5" data-program-id={p.id}>
                <div>
                  <p className="font-medium">
                    {p.name} {p.active ? <Badge tone="ok">Active</Badge> : null}
                  </p>
                  <p className="text-xs text-muted">
                    {label(p.goal)} · {p.days_per_week} days · {p.weeks} weeks
                  </p>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={() => void edit(p.id)} disabled={busy !== null} aria-label={`Edit ${p.name}`}>
                    Edit
                  </button>
                  {p.active ? null : (
                    <button type="button" className={`${buttonClass} min-h-11`} onClick={() => void activate(p.id)} disabled={busy !== null} aria-label={`Activate ${p.name}`}>
                      Activate
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

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
            setError(null);
          }}
        />
      )}
    </div>
  );
}

function detailText(error: string, detail: unknown): string {
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : "")).filter(Boolean);
    if (parts.length > 0) return parts.join(". ");
  }
  return typeof detail === "string" ? detail : error;
}

function GenerateForm({ onPreview }: { onPreview: (preview: ProgramPreview) => void }) {
  const [days, setDays] = useState(4);
  const [goal, setGoal] = useState<ProgramGoal>("hypertrophy");
  const [equipment, setEquipment] = useState<Equipment[]>(["barbell", "dumbbell"]);
  const [minutes, setMinutes] = useState("60");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    const session = Number(minutes);
    if (!Number.isInteger(session) || session < 20 || session > 180) return setError("Minutes per session: 20 to 180");
    setBusy(true);
    setError(null);
    const body: GenerateIn = { days_per_week: days, goal, equipment, session_minutes: session, weeks: 8 };
    const result = await post<ProgramPreview>("/v1/training/programs/generate", body);
    setBusy(false);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : detailText(result.error, result.detail));
    onPreview(result.data);
  }

  return (
    <Card title="Generate a program" labelledBy="generate-title">
      <form onSubmit={(e) => void generate(e)} className="space-y-4" aria-labelledby="generate-title">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block text-sm font-medium">
            Days per week
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={`${inputClass} mt-1 min-h-11`}>
              {DAY_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d} days{d === 4 ? " (upper/lower)" : d === 6 ? " (push/pull/legs)" : d === 2 ? " (full body)" : " (full body)"}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Goal
            <select value={goal} onChange={(e) => setGoal(e.target.value as ProgramGoal)} className={`${inputClass} mt-1 min-h-11`}>
              {GOALS.map((g) => (
                <option key={g} value={g}>
                  {label(g)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Minutes per session
            <input inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} className={`${inputClass} mt-1 min-h-11`} />
          </label>
        </div>
        <fieldset>
          <legend className="text-sm font-medium">Equipment (bodyweight is always included)</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {EQUIPMENT.filter((e) => e !== "bodyweight").map((e) => (
              <label key={e} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border px-3 text-sm">
                <input
                  type="checkbox"
                  checked={equipment.includes(e)}
                  onChange={(event) => setEquipment((list) => (event.target.checked ? [...list, e] : list.filter((x) => x !== e)))}
                  name={`${id}-equipment`}
                />
                {label(e)}
              </label>
            ))}
          </div>
        </fieldset>
        {error ? <ErrorState title="Could not generate" message={error} /> : null}
        <button type="submit" className={`${buttonClass} min-h-11`} disabled={busy}>
          {busy ? "Generating…" : "Generate preview"}
        </button>
      </form>
    </Card>
  );
}

function ProgramEditor({
  draft,
  minutes,
  exercises,
  onChange,
  onSave,
  onCancel,
  saving,
}: {
  draft: DraftProgram;
  minutes: number[] | null;
  exercises: Exercise[];
  onChange: (draft: DraftProgram) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [picking, setPicking] = useState<string | null>(null);
  const setDay = (key: string, change: (day: DraftDay) => DraftDay) =>
    onChange({ ...draft, days: draft.days.map((d) => (d.key === key ? change(d) : d)) });

  return (
    <Card title={draft.id ? "Edit program" : "Preview"} labelledBy="editor-title">
      <div className="space-y-5" data-testid="program-editor">
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <label className="block text-sm font-medium">
            Program name
            <input value={draft.name} onChange={(e) => onChange({ ...draft, name: e.target.value })} className={`${inputClass} mt-1 min-h-11`} />
          </label>
          <label className="block text-sm font-medium">
            Weeks
            <input inputMode="numeric" value={draft.weeks} onChange={(e) => onChange({ ...draft, weeks: e.target.value })} className={`${inputClass} mt-1 min-h-11`} />
          </label>
        </div>
        {draft.days.map((day, d) => (
          <fieldset key={day.key} className="min-w-0 rounded-xl border border-border p-3" data-testid="editor-day">
            <legend className="px-1 text-sm font-semibold">
              Day {d + 1}
              {minutes?.[d] !== undefined ? <span className="font-normal text-muted"> · about {Math.round(minutes[d] ?? 0)} min</span> : null}
            </legend>
            <label className="block text-xs font-medium text-muted">
              Day name
              <input value={day.name} onChange={(e) => setDay(day.key, (x) => ({ ...x, name: e.target.value }))} className={`${inputClass} mt-1`} />
            </label>
            <ol className="mt-3 space-y-3">
              {day.exercises.map((e, i) => (
                <ExerciseRow
                  key={e.key}
                  exercise={e}
                  first={i === 0}
                  last={i === day.exercises.length - 1}
                  onChange={(change) =>
                    setDay(day.key, (x) => ({ ...x, exercises: x.exercises.map((y) => (y.key === e.key ? { ...y, ...change } : y)) }))
                  }
                  onMove={(delta) => setDay(day.key, (x) => ({ ...x, exercises: move(x.exercises, i, delta) }))}
                  onRemove={() => setDay(day.key, (x) => ({ ...x, exercises: x.exercises.filter((y) => y.key !== e.key) }))}
                />
              ))}
            </ol>
            {picking === day.key ? (
              <div className="mt-3">
                <ExercisePicker
                  exercises={exercises}
                  onCancel={() => setPicking(null)}
                  onPick={(exercise) => {
                    setDay(day.key, (x) => ({ ...x, exercises: [...x.exercises, newExercise(exercise)] }));
                    setPicking(null);
                  }}
                />
              </div>
            ) : (
              <button type="button" className="mt-2 min-h-11 rounded-lg px-3 text-sm font-medium text-accent hover:bg-surface-2" onClick={() => setPicking(day.key)}>
                Add exercise to {day.name || `day ${d + 1}`}
              </button>
            )}
          </fieldset>
        ))}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={`${buttonClass} min-h-11`} onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : draft.id ? "Save changes" : "Save program"}
          </button>
          <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={onCancel}>
            {draft.id ? "Cancel" : "Discard preview"}
          </button>
        </div>
      </div>
    </Card>
  );
}

function ExerciseRow({
  exercise,
  first,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  exercise: DraftExercise;
  first: boolean;
  last: boolean;
  onChange: (change: Partial<DraftExercise>) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const small = "min-h-11 min-w-11 rounded-lg border border-border text-sm disabled:opacity-40";
  const field = (name: keyof DraftExercise, text: string, mode: "numeric" | "decimal" = "numeric") => (
    <label className="block min-w-0 text-xs text-muted">
      <span className="block truncate">{text}</span>
      <input
        inputMode={mode}
        value={String(exercise[name])}
        onChange={(e) => onChange({ [name]: e.target.value } as Partial<DraftExercise>)}
        aria-label={`${text}, ${exercise.name}`}
        className="mt-0.5 h-11 w-full min-w-0 rounded-lg border border-border bg-surface px-1 text-center text-sm text-text tabular-nums"
      />
    </label>
  );
  return (
    <li className="rounded-lg bg-surface-2/60 p-2" data-testid="editor-exercise">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-medium">{exercise.name}</p>
        <div className="flex shrink-0 gap-1">
          <button type="button" className={small} onClick={() => onMove(-1)} disabled={first} aria-label={`Move ${exercise.name} up`}>
            ↑
          </button>
          <button type="button" className={small} onClick={() => onMove(1)} disabled={last} aria-label={`Move ${exercise.name} down`}>
            ↓
          </button>
          <button type="button" className={small} onClick={onRemove} aria-label={`Remove ${exercise.name}`}>
            ✕
          </button>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-5 gap-1.5">
        {field("sets", "Sets")}
        {field("repMin", "Reps min")}
        {field("repMax", "Reps max")}
        {field("restSeconds", "Rest s")}
        {field("startWeightKg", "Start kg", "decimal")}
      </div>
    </li>
  );
}
