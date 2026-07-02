"use client";
import { useDebate } from "@/store/debate";

const CARDS = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
      </svg>
    ),
    title: "Debate the AI",
    body: "An opponent that argues back intelligently — adapting its strategy to your style, pushing harder on your weakest points every round.",
    action: "Start a debate →",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: "Get scored instantly",
    body: "Real-time breakdown after every exchange — logic, evidence, rhetoric. See precisely where your argument held up and where it collapsed.",
    action: "See how scoring works →",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
      </svg>
    ),
    title: "Build your mastery graph",
    body: "Cognee maps your argument history into a personal knowledge graph. The AI remembers every session and gets sharper about your patterns over time.",
    action: "View your progress →",
  },
];

export default function LandingPage() {
  const setScreen = useDebate((s) => s.setScreen);

  return (
    <div className="min-h-screen bg-chalk font-sans text-ink antialiased">

      {/* ── Nav ── */}
      <header className="sticky top-0 z-40 bg-chalk/95 backdrop-blur-sm border-b border-border">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-scarlet rounded flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <span className="font-semibold text-sm text-ink tracking-tight">DebateMind</span>
          </div>
          <button
            onClick={() => setScreen("auth")}
            className="bg-scarlet text-white text-sm font-medium px-4 py-1.5 rounded-md hover:bg-scarlet/90 transition-colors"
          >
            Sign in
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="pt-20 pb-16 px-6 text-center">
        <div className="max-w-3xl mx-auto">
          {/* Badge */}
          <div className="inline-flex items-center gap-1.5 bg-white border border-border rounded-full px-3 py-1 text-xs text-fog mb-8">
            <svg className="w-3 h-3 text-scarlet" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            AI debate partner with a persistent memory
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-5xl font-bold text-ink leading-tight tracking-tight mb-5">
            Practice arguing — and never<br />
            <span className="text-scarlet">repeat the same mistake twice.</span>
          </h1>

          {/* Sub */}
          <p className="text-fog text-base md:text-lg max-w-xl mx-auto leading-relaxed mb-8">
            DebateMind is an AI opponent that debates you in real time, scores every exchange, and uses Cognee to build a memory graph of your argument patterns across every session.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={() => setScreen("auth")}
              className="bg-scarlet text-white text-sm font-semibold px-6 py-2.5 rounded-lg hover:bg-scarlet/90 transition-colors"
            >
              Start arguing →
            </button>
            <a
              href="#how-it-works"
              className="bg-white border border-border text-ink text-sm font-medium px-6 py-2.5 rounded-lg hover:bg-border/30 transition-colors"
            >
              See how it works
            </a>
          </div>
        </div>
      </section>

      {/* ── 3-card row ── */}
      <section className="pb-20 px-6">
        <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-4">
          {CARDS.map((c) => (
            <div key={c.title} className="bg-white border border-border rounded-xl p-6 flex flex-col gap-3">
              <div className="w-9 h-9 rounded-lg bg-chalk border border-border flex items-center justify-center text-fog">
                {c.icon}
              </div>
              <h3 className="font-semibold text-ink text-sm">{c.title}</h3>
              <p className="text-fog text-sm leading-relaxed flex-1">{c.body}</p>
              <button
                onClick={() => setScreen("auth")}
                className="text-scarlet text-sm font-medium text-left hover:underline"
              >
                {c.action}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* ── Problem ── */}
      <section className="bg-white border-y border-border py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3">The problem</p>
          <div className="md:flex md:items-start md:gap-16">
            <h2 className="text-2xl font-bold text-ink leading-snug mb-6 md:mb-0 md:w-64 flex-shrink-0">
              Debate practice is broken.
            </h2>
            <div className="grid sm:grid-cols-3 gap-6 flex-1">
              {[
                { label: "No memory", detail: "Every session resets. Coaches and static tools forget what you've already practised." },
                { label: "No personalisation", detail: "Generic feedback misses your specific patterns, blind spots, and recurring fallacies." },
                { label: "No accountability", detail: "Without mastery tracking, progress is invisible and habits never actually change." },
              ].map((p) => (
                <div key={p.label}>
                  <div className="w-5 h-5 rounded-full bg-scarlet/10 flex items-center justify-center mb-3">
                    <span className="text-scarlet text-xs font-bold leading-none">×</span>
                  </div>
                  <p className="text-sm font-semibold text-ink mb-1">{p.label}</p>
                  <p className="text-sm text-fog leading-relaxed">{p.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3">How it works</p>
          <h2 className="text-2xl font-bold text-ink mb-10">Four steps to sharper thinking</h2>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-6">
            {[
              { n: "01", label: "Pick a topic", detail: "Choose from 50+ debate topics or enter your own. Politics, ethics, science, law — any side." },
              { n: "02", label: "Argue your case", detail: "The AI counters every point with structured rebuttals. Text or voice — your choice." },
              { n: "03", label: "Get scored", detail: "Instant feedback on logic, evidence, and rhetoric after every exchange." },
              { n: "04", label: "Get remembered", detail: "Cognee builds your argument graph. Next session, the AI knows exactly where to push you harder." },
            ].map((s) => (
              <div key={s.n} className="flex flex-col gap-2">
                <span className="text-3xl font-bold text-border font-mono">{s.n}</span>
                <p className="text-sm font-semibold text-ink">{s.label}</p>
                <p className="text-sm text-fog leading-relaxed">{s.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Cognee section ── */}
      <section className="px-6 pb-16">
        <div className="max-w-5xl mx-auto">
          <div className="bg-slate rounded-2xl overflow-hidden">
            <div className="p-8 md:p-12 md:flex md:gap-12 md:items-start">
              {/* Left */}
              <div className="flex-1 mb-8 md:mb-0">
                <div className="inline-flex items-center gap-1.5 bg-ember/20 text-ember text-xs font-semibold uppercase tracking-widest px-3 py-1 rounded-full mb-5">
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.337.208-.462.477-.63C13.6 12.753 14 11.763 14 11a4 4 0 10-8 0c0 .763.4 1.753 1.523 2.37.27.168.462.293.477.63h4z" />
                  </svg>
                  Built with Cognee
                </div>
                <h2 className="text-2xl font-bold text-white leading-snug mb-3">
                  A memory that actually understands how you argue
                </h2>
                <p className="text-white/60 text-sm leading-relaxed mb-6">
                  Cognee is an AI memory framework that builds structured knowledge graphs from your sessions. DebateMind uses it to track not just <em>what</em> you've debated, but <em>how</em> — patterns, fallacies, strengths, and blind spots — so every session builds on the last.
                </p>
                <ul className="space-y-2.5">
                  {[
                    "Argument patterns tracked across every session",
                    "Knowledge graph of debated and mastered topics",
                    "Fallacy detection fed back into the AI's strategy",
                    "Mastery scores that evolve as you improve",
                  ].map((item) => (
                    <li key={item} className="flex items-start gap-2.5 text-white/70 text-sm">
                      <svg className="w-4 h-4 text-verdant flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Right — stat cards */}
              <div className="flex md:flex-col gap-3 flex-wrap md:w-44 flex-shrink-0">
                {[
                  { value: "∞", label: "Arguments tracked", sub: "across every session" },
                  { value: "50+", label: "Topics indexed", sub: "and growing" },
                  { value: "Live", label: "Pattern detection", sub: "per exchange" },
                ].map((s) => (
                  <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4 flex-1 md:flex-none">
                    <p className="text-white text-2xl font-bold mb-0.5">{s.value}</p>
                    <p className="text-white text-xs font-semibold">{s.label}</p>
                    <p className="text-white/40 text-xs">{s.sub}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Getting started ── */}
      <section className="bg-white border-y border-border py-14 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3">Quick start</p>
          <h2 className="text-2xl font-bold text-ink mb-8">Up and running in two minutes</h2>
          <div className="grid sm:grid-cols-3 gap-8">
            {[
              { n: "1", heading: "Create your account", body: "Sign up and complete a short calibration session so DebateMind can baseline your argumentation style." },
              { n: "2", heading: "Pick your first topic", body: "Browse curated topics by category, or search for one you care about. Choose a side — or let the AI assign one." },
              { n: "3", heading: "Debate, score, improve", body: "Exchange arguments in real time. Each session sharpens your Cognee graph and the AI grows harder to beat." },
            ].map((g) => (
              <div key={g.n} className="flex gap-3">
                <div className="w-6 h-6 rounded-full bg-scarlet text-white text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                  {g.n}
                </div>
                <div>
                  <p className="text-sm font-semibold text-ink mb-1">{g.heading}</p>
                  <p className="text-sm text-fog leading-relaxed">{g.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-20 px-6 text-center">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-ink mb-3 leading-tight">Ready to argue better?</h2>
          <p className="text-fog text-base mb-8">
            Start debating today. The AI remembers every session — and gets tougher every time.
          </p>
          <button
            onClick={() => setScreen("auth")}
            className="bg-scarlet text-white text-sm font-semibold px-8 py-3 rounded-lg hover:bg-scarlet/90 transition-colors"
          >
            Start arguing for free →
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border py-6 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-scarlet rounded flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-ink">DebateMind</span>
          </div>
          <p className="text-fog text-xs">Built with Cognee · The AI that learns how you argue</p>
        </div>
      </footer>
    </div>
  );
}
