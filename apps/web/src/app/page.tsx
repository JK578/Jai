import { getBackendStatus } from "../lib/backend";

export const dynamic = "force-dynamic";

export default async function Home() {
  const status = await getBackendStatus();
  const label = {
    ready: "Connected · backend ready",
    not_ready: "Connected · backend not ready",
    unavailable: "Backend unavailable",
  }[status];

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-8 py-12">
      <header className="flex items-center justify-between border-b border-slate-800 pb-6">
        <span className="text-xl font-semibold tracking-tight">IncidentIQ</span>
        <span className="text-sm text-slate-400">Development workspace</span>
      </header>
      <section className="my-auto py-20">
        <p className="mb-5 text-sm font-medium uppercase tracking-widest text-teal-400">Platform foundation</p>
        <h1 className="max-w-2xl text-5xl font-semibold leading-tight">A clearer path from incident to insight.</h1>
        <p className="mt-6 max-w-xl text-lg text-slate-400">The investigation workspace starts here. API connectivity is available; investigation features arrive in future milestones.</p>
        <div className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="text-sm text-slate-400">Backend connectivity</h2>
          <p role="status" className={`mt-2 text-lg ${status === "ready" ? "text-teal-400" : "text-amber-300"}`}>{label}</p>
          <p className="mt-3 text-sm text-slate-400">Refresh this page to check again.</p>
        </div>
      </section>
      <footer className="text-sm text-slate-500">Phase 0 + Phase 1 foundation · Local development</footer>
    </main>
  );
}
