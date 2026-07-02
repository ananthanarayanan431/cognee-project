"use client";
import { SignInButton } from "@clerk/nextjs";
import { useDebate } from "@/store/debate";

const CARDS = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
      </svg>
    ),
    title: "An opponent that adapts to you",
    body: "The AI reads your argumentative patterns and targets your weakest reasoning in every exchange — logic gaps, evidence gaps, rhetorical habits.",
    stat: "3 scoring dimensions per exchange",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    title: "Scored on what actually matters",
    body: "Instant breakdown after every exchange — logic, evidence, rhetoric, and fallacy detection. See exactly where your argument held and where it broke.",
    stat: "20+ logical fallacy types detected",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
      </svg>
    ),
    title: "Memory that compounds across sessions",
    body: "Cognee maps every argument into a persistent knowledge graph. The AI remembers every session and gets harder to beat the more you practise.",
    stat: "Powered by 1M+ Cognee pipelines/month",
  },
];

const STATS = [
  { value: "44%", label: "critical thinking improvement", source: "meta-analysis, debate participation" },
  { value: "+12pp", label: "leadership advancement", source: "MIT Sloan / Fortune 100 study, 2025" },
  { value: "20+", label: "fallacy types detected", source: "per session, in real time" },
  { value: "1M+", label: "Cognee pipelines/month", source: "powering DebateMind's memory layer" },
];

const FALLACIES = [
  "Ad Hominem", "Straw Man", "False Dilemma", "Hasty Generalisation",
  "Appeal to Authority", "Circular Reasoning", "Red Herring", "Slippery Slope",
  "Post Hoc", "Bandwagon", "False Equivalence", "Appeal to Ignorance",
];

export default function LandingPage() {
  const { token, setScreen } = useDebate();
  const isAuthenticated = !!token;

  function goToApp() {
    setScreen("topic");
    window.history.pushState({ screen: "topic" }, "", "/");
  }

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
          <nav className="hidden md:flex items-center gap-6 text-sm text-fog">
            <a href="#how-it-works" className="hover:text-ink transition-colors">How it works</a>
            <a href="#research" className="hover:text-ink transition-colors">Research</a>
            <a href="#cognee" className="hover:text-ink transition-colors">Memory</a>
          </nav>
          {isAuthenticated ? (
            <button
              onClick={goToApp}
              className="bg-scarlet text-white text-sm font-medium px-4 py-1.5 rounded-md hover:bg-scarlet/90 transition-colors"
            >
              Open app →
            </button>
          ) : (
            <SignInButton mode="redirect">
              <button className="bg-scarlet text-white text-sm font-medium px-4 py-1.5 rounded-md hover:bg-scarlet/90 transition-colors">
                Sign in
              </button>
            </SignInButton>
          )}
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="pt-20 pb-14 px-6 text-center">
        <div className="max-w-3xl mx-auto">
          {/* Badge */}
          <div className="inline-flex items-center gap-1.5 bg-white border border-border rounded-full px-3 py-1 text-xs text-fog mb-8">
            <span className="w-1.5 h-1.5 rounded-full bg-verdant inline-block" />
            Research-backed · AI debate partner with persistent memory
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-[52px] font-bold text-ink leading-tight tracking-tight mb-5">
            Argue better.<br />
            <span className="text-scarlet">Never repeat the same mistake.</span>
          </h1>

          {/* Sub */}
          <p className="text-fog text-base md:text-lg max-w-xl mx-auto leading-relaxed mb-8">
            DebateMind is an AI opponent that debates you in real time, scores every exchange on logic, evidence, and rhetoric, and uses a persistent memory graph to get harder to beat every session.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center mb-10">
            {isAuthenticated ? (
              <button
                onClick={goToApp}
                className="bg-scarlet text-white text-sm font-semibold px-6 py-2.5 rounded-lg hover:bg-scarlet/90 transition-colors"
              >
                Open DebateMind →
              </button>
            ) : (
              <SignInButton mode="redirect">
                <button className="bg-scarlet text-white text-sm font-semibold px-6 py-2.5 rounded-lg hover:bg-scarlet/90 transition-colors">
                  Start arguing for free →
                </button>
              </SignInButton>
            )}
            <a
              href="#how-it-works"
              className="bg-white border border-border text-ink text-sm font-medium px-6 py-2.5 rounded-lg hover:bg-border/30 transition-colors"
            >
              See how it works
            </a>
          </div>

          {/* Trust strip */}
          <p className="text-xs text-fog">
            Powered by Cognee · Trusted by debaters, students, and professionals
          </p>
        </div>
      </section>

      {/* ── Stats strip ── */}
      <section id="research" className="bg-white border-y border-border py-10 px-6">
        <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6">
          {STATS.map((s) => (
            <div key={s.value} className="text-center md:text-left md:border-r md:border-border last:border-r-0 md:pr-6 last:pr-0">
              <p className="text-2xl font-bold text-scarlet mb-0.5">{s.value}</p>
              <p className="text-sm font-semibold text-ink mb-0.5">{s.label}</p>
              <p className="text-[11px] text-fog leading-snug">{s.source}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 3-card row ── */}
      <section className="py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3 text-center">What you get</p>
          <h2 className="text-2xl font-bold text-ink mb-10 text-center">Built differently from every other debate tool</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {CARDS.map((c) => (
              <div key={c.title} className="bg-white border border-border rounded-xl p-6 flex flex-col gap-3">
                <div className="w-9 h-9 rounded-lg bg-chalk border border-border flex items-center justify-center text-fog">
                  {c.icon}
                </div>
                <h3 className="font-semibold text-ink text-sm">{c.title}</h3>
                <p className="text-fog text-sm leading-relaxed flex-1">{c.body}</p>
                <p className="text-[11px] text-scarlet font-semibold">{c.stat}</p>
                {isAuthenticated ? (
                  <button onClick={goToApp} className="text-scarlet text-sm font-medium text-left hover:underline">
                    Open app →
                  </button>
                ) : (
                  <SignInButton mode="redirect">
                    <button className="text-scarlet text-sm font-medium text-left hover:underline">
                      Get started →
                    </button>
                  </SignInButton>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Problem ── */}
      <section className="bg-white border-y border-border py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3">The problem</p>
          <div className="md:flex md:items-start md:gap-16">
            <h2 className="text-2xl font-bold text-ink leading-snug mb-6 md:mb-0 md:w-64 flex-shrink-0">
              Every other tool forgets you the moment you leave.
            </h2>
            <div className="grid sm:grid-cols-3 gap-6 flex-1">
              {[
                { label: "No cross-session memory", detail: "Coaches and static apps reset every time. You practise the same mistakes indefinitely because nothing tracks your history." },
                { label: "Generic feedback", detail: "Scoring one exchange at a time misses the patterns — the recurring fallacies and blind spots that define your style." },
                { label: "No compounding progress", detail: "Without a persistent model of how you argue, every session starts from zero and habits never actually change." },
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
          <h2 className="text-2xl font-bold text-ink mb-10">From first argument to mastery — in four steps</h2>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-6">
            {[
              { n: "01", label: "Calibrate your style", detail: "A 3-question baseline session maps your opening argument patterns so the AI knows exactly where you stand." },
              { n: "02", label: "Pick a topic, take a side", detail: "Choose from 50+ curated topics across policy, ethics, technology, and society — or enter your own." },
              { n: "03", label: "Debate and get scored", detail: "Real-time scoring on logic, evidence, and rhetoric after every exchange. Fallacies flagged as they happen." },
              { n: "04", label: "The AI remembers", detail: "Cognee builds your personal argument graph. Every session sharpens its model of your blind spots — and gets harder to beat." },
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

      {/* ── Fallacy detection strip ── */}
      <section className="bg-white border-y border-border py-12 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center md:gap-12">
            <div className="mb-6 md:mb-0 md:w-56 flex-shrink-0">
              <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-2">Fallacy detection</p>
              <h3 className="text-xl font-bold text-ink leading-snug">Catch faulty reasoning before it becomes a habit</h3>
            </div>
            <div className="flex flex-wrap gap-2 flex-1">
              {FALLACIES.map((f) => (
                <span
                  key={f}
                  className="text-[11px] font-medium text-fog border border-border rounded-full px-3 py-1 bg-chalk"
                >
                  {f}
                </span>
              ))}
              <span className="text-[11px] font-medium text-scarlet border border-scarlet/20 rounded-full px-3 py-1 bg-scarlet/5">
                + more
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Research / Social proof ── */}
      <section className="py-16 px-6">
        <div className="max-w-5xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-scarlet mb-3">The research</p>
          <h2 className="text-2xl font-bold text-ink mb-10">Why debate training works</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              {
                stat: "44%",
                heading: "Stronger critical thinking",
                body: "A meta-analysis of debate participation studies found critical thinking skills improve by up to 44% compared to non-participants.",
                source: "debatbond.nl meta-analysis",
              },
              {
                stat: "+12pp",
                heading: "Higher leadership advancement",
                body: "In a Fortune 100 longitudinal experiment, employees who received 9 weeks of debate training were 12 percentage points more likely to advance to leadership roles 18 months later.",
                source: "MIT Sloan / Journal of Applied Psychology, 2025",
              },
              {
                stat: "68%",
                heading: "Of a full year's learning gains",
                body: "Boston Public Schools research found debate participation improved ELA test scores by 0.13 SD — equivalent to 68% of a full year of 9th grade learning.",
                source: "Boston Public Schools longitudinal study",
              },
            ].map((r) => (
              <div key={r.stat} className="bg-white border border-border rounded-xl p-6">
                <p className="text-3xl font-bold text-scarlet mb-2">{r.stat}</p>
                <p className="text-sm font-semibold text-ink mb-2">{r.heading}</p>
                <p className="text-sm text-fog leading-relaxed mb-4">{r.body}</p>
                <p className="text-[10px] text-fog/60 uppercase tracking-wide">{r.source}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Cognee section ── */}
      <section id="cognee" className="px-6 pb-16">
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
                  A memory layer that understands how you argue
                </h2>
                <p className="text-white/60 text-sm leading-relaxed mb-6">
                  Cognee is an AI memory framework running over one million pipelines each month, adopted by more than 70 companies including Bayer. DebateMind uses it to build a structured knowledge graph of your argument patterns — tracking not just <em>what</em> you&apos;ve debated, but <em>how</em> — so every session builds on the last.
                </p>
                <ul className="space-y-2.5">
                  {[
                    "Argument patterns and fallacies tracked across every session",
                    "Personal knowledge graph of debated and mastered topics",
                    "Fallacy detection fed back into the AI opponent's strategy",
                    "Mastery scores and spaced-repetition scheduling that evolve as you improve",
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
                  { value: "1M+", label: "Pipelines per month", sub: "powering the memory layer" },
                  { value: "70+", label: "Companies using Cognee", sub: "including Bayer" },
                  { value: "Live", label: "Pattern detection", sub: "per exchange, every session" },
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
          <h2 className="text-2xl font-bold text-ink mb-8">Up and arguing in two minutes</h2>
          <div className="grid sm:grid-cols-3 gap-8">
            {[
              { n: "1", heading: "Create your account", body: "Sign up free and complete a 3-question calibration so DebateMind can baseline your argument style and set the AI's initial difficulty." },
              { n: "2", heading: "Pick a topic and a side", body: "Browse curated topics by domain — policy, ethics, technology, society — or enter your own. Take a side or let the AI assign one." },
              { n: "3", heading: "Debate, score, and compound", body: "Exchange arguments in real time. Each session deepens your Cognee graph, tightens the AI's model of your weaknesses, and makes you sharper." },
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
          <div className="inline-flex items-center gap-1.5 bg-white border border-border rounded-full px-3 py-1 text-xs text-fog mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-verdant inline-block" />
            Free to start · No credit card required
          </div>
          <h2 className="text-3xl font-bold text-ink mb-3 leading-tight">
            The AI that argues back — and remembers everything.
          </h2>
          <p className="text-fog text-base mb-8">
            Start your first debate today. Every session builds the memory graph that makes the next one harder.
          </p>
          {isAuthenticated ? (
            <button
              onClick={goToApp}
              className="bg-scarlet text-white text-sm font-semibold px-8 py-3 rounded-lg hover:bg-scarlet/90 transition-colors"
            >
              Open DebateMind →
            </button>
          ) : (
            <SignInButton mode="redirect">
              <button className="bg-scarlet text-white text-sm font-semibold px-8 py-3 rounded-lg hover:bg-scarlet/90 transition-colors">
                Start arguing for free →
              </button>
            </SignInButton>
          )}
          <p className="text-xs text-fog mt-4">
            Debate participation improves critical thinking by up to 44% — meta-analysis of debate studies
          </p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border py-8 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-scarlet rounded flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-ink">DebateMind</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-fog">
            <span>Built with Cognee memory framework</span>
            <span>·</span>
            <span>Debate training backed by MIT, Boston Public Schools research</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
