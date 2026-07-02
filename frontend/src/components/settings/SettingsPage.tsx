"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  IconArrowLeft,
  IconCheck,
  IconChevronDown,
  IconGavel,
  IconRobot,
  IconSearch,
  IconX,
} from "@tabler/icons-react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";

type ModelMeta = {
  id: string;
  name: string;
  provider: string;
  context_length: number | null;
  prompt_price_per_m: number;
};

function fmtPrice(n: number) {
  if (n === 0) return "Free";
  if (n < 0.01) return `$${n.toFixed(4)}/1M`;
  return `$${n.toFixed(2)}/1M`;
}

function fmtCtx(n: number | null) {
  if (!n) return null;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(0)}M ctx`;
  return `${(n / 1_000).toFixed(0)}K ctx`;
}

// ── Inline model dropdown ─────────────────────────────────────────────────────

function ModelDropdown({
  models,
  selected,
  placeholder,
  onSelect,
}: {
  models: ModelMeta[];
  selected: string;
  placeholder: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen]     = useState(false);
  const [search, setSearch] = useState("");
  const ref                 = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return q
      ? models.filter((m) => m.name.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q) || m.id.toLowerCase().includes(q))
      : models;
  }, [models, search]);

  const byProvider = useMemo(() => {
    const map: Record<string, ModelMeta[]> = {};
    for (const m of filtered) (map[m.provider] ??= []).push(m);
    return map;
  }, [filtered]);

  const selectedModel = models.find((m) => m.id === selected);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-fog/5 hover:bg-fog/8 border border-border hover:border-fog/40 rounded-xl transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          {selectedModel ? (
            <>
              <p className="font-sans text-[13px] text-ink truncate">{selectedModel.name}</p>
              <p className="font-sans text-[10px] text-fog mt-0.5">{selectedModel.id}</p>
            </>
          ) : (
            <p className="font-sans text-[13px] text-fog">{placeholder}</p>
          )}
        </div>
        <IconChevronDown
          size={15}
          className={`text-fog flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute z-50 left-0 right-0 mt-2 bg-white border border-border rounded-xl shadow-xl overflow-hidden">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <IconSearch size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fog/50 pointer-events-none" />
              <input
                autoFocus
                type="text"
                placeholder="Search models…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full bg-fog/5 border border-border rounded-lg pl-7 pr-7 py-1.5 font-sans text-[12px] text-ink placeholder:text-fog/50 outline-none focus:border-scarlet transition-colors"
              />
              {search && (
                <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fog/50 hover:text-fog">
                  <IconX size={11} />
                </button>
              )}
            </div>
          </div>

          <div className="overflow-y-auto max-h-[320px] p-2">
            {Object.keys(byProvider).length === 0 && (
              <p className="font-sans text-[12px] text-fog text-center py-6">No results for &ldquo;{search}&rdquo;</p>
            )}
            {Object.entries(byProvider).map(([provider, providerModels]) => (
              <div key={provider} className="mb-3">
                <p className="font-sans text-[9px] font-semibold uppercase tracking-widest text-fog/50 px-2 py-1 sticky top-0 bg-white">
                  {provider}
                </p>
                {providerModels.map((m) => {
                  const isSel = m.id === selected;
                  return (
                    <button
                      key={m.id}
                      onClick={() => { onSelect(m.id); setOpen(false); setSearch(""); }}
                      className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg transition-colors text-left group ${
                        isSel ? "bg-scarlet/8" : "hover:bg-fog/5"
                      }`}
                    >
                      <div className="flex-1 min-w-0 mr-3">
                        <p className={`font-sans text-[12px] truncate ${isSel ? "text-ink font-medium" : "text-fog group-hover:text-ink"}`}>
                          {m.name}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="font-sans text-[9px] text-fog/50 tabular-nums">{fmtPrice(m.prompt_price_per_m)}</span>
                          {fmtCtx(m.context_length) && (
                            <span className="font-sans text-[9px] text-fog/40">· {fmtCtx(m.context_length)}</span>
                          )}
                        </div>
                      </div>
                      {isSel && <IconCheck size={12} className="text-scarlet flex-shrink-0" />}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Role card ─────────────────────────────────────────────────────────────────

function RoleCard({
  icon,
  title,
  description,
  usedFor,
  models,
  selected,
  defaultId,
  loading,
  onSelect,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  usedFor: string[];
  models: ModelMeta[];
  selected: string | null;
  defaultId: string;
  loading: boolean;
  onSelect: (id: string) => void;
}) {
  const effectiveSelected = selected || defaultId;
  const isCustom = selected && selected !== defaultId;

  return (
    <div className="bg-fog/[0.03] border border-border rounded-2xl p-5 flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-fog/5 border border-border flex items-center justify-center flex-shrink-0">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-sans text-[14px] font-semibold text-ink">{title}</h3>
            {isCustom && (
              <span className="font-sans text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-scarlet/10 text-scarlet border border-scarlet/20">
                Custom
              </span>
            )}
          </div>
          <p className="font-sans text-[12px] text-fog mt-0.5 leading-relaxed">{description}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {usedFor.map((label) => (
          <span
            key={label}
            className="font-sans text-[10px] text-fog bg-fog/5 border border-border rounded-full px-2.5 py-1"
          >
            {label}
          </span>
        ))}
      </div>

      {loading ? (
        <div className="h-[52px] bg-fog/5 rounded-xl animate-pulse" />
      ) : (
        <ModelDropdown
          models={models}
          selected={effectiveSelected}
          placeholder="Select a model…"
          onSelect={onSelect}
        />
      )}

      {isCustom && (
        <button
          onClick={() => onSelect(defaultId)}
          className="font-sans text-[11px] text-fog/60 hover:text-fog transition-colors text-left"
        >
          Reset to default ({models.find((m) => m.id === defaultId)?.name ?? defaultId})
        </button>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { setScreen, mainModel, setMainModel, judgeModel, setJudgeModel } = useDebate();
  const [models, setModels]         = useState<ModelMeta[]>([]);
  const [defaultOpponent, setDefOpp] = useState("");
  const [defaultJudge, setDefJudge]  = useState("");
  const [loading, setLoading]        = useState(true);

  useEffect(() => {
    api.getModels()
      .then((d) => {
        setModels(d.models);
        setDefOpp(d.default_opponent);
        setDefJudge(d.default_judge);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col h-full bg-chalk overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-border flex-shrink-0 bg-white">
        <button
          onClick={() => setScreen("topic")}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-fog/60 hover:text-ink hover:bg-fog/5 transition-colors"
        >
          <IconArrowLeft size={16} />
        </button>
        <div>
          <h1 className="font-sans text-[15px] font-semibold text-ink">Settings</h1>
          <p className="font-sans text-[11px] text-fog">Configure your debate experience</p>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-8 flex flex-col gap-8">

          <section>
            <div className="mb-4">
              <p className="font-sans text-[11px] font-semibold uppercase tracking-widest text-fog/60 mb-1">
                AI Models
              </p>
              <p className="font-sans text-[13px] text-fog leading-relaxed">
                Choose which models power each role. Changes take effect on the next turn.
              </p>
            </div>

            <div className="flex flex-col gap-3">
              <RoleCard
                icon={<IconRobot size={16} className="text-fog" />}
                title="Opponent"
                description="Argues against you in every debate turn."
                usedFor={["Generates opponent responses", "Adapts to your argument style", "Difficulty-aware"]}
                models={models}
                selected={mainModel}
                defaultId={defaultOpponent}
                loading={loading}
                onSelect={setMainModel}
              />

              <RoleCard
                icon={<IconGavel size={16} className="text-fog" />}
                title="Judge & Evaluator"
                description="Scores your arguments, detects fallacies, and builds your profile."
                usedFor={["Logic / evidence / rhetoric scores", "Fallacy detection", "Pattern extraction", "Describe me"]}
                models={models}
                selected={judgeModel}
                defaultId={defaultJudge}
                loading={loading}
                onSelect={setJudgeModel}
              />
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}
