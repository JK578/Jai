import { getBackendHealth } from "../lib/backend";
import IncidentWorkspace from "../components/incident-workspace";

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getBackendHealth();
  const status = health.status;
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
      <section className="py-10">
        <p className="mb-5 text-sm font-medium uppercase tracking-widest text-teal-400">Platform foundation</p>
        <h1 className="max-w-2xl text-4xl font-semibold leading-tight">Incident workspace</h1>
        <p className="mt-4 text-amber-200">{health.storage === "postgres"
          ? "Incidents are saved to PostgreSQL and retained across backend restarts."
          : health.storage === "memory"
          ? "Temporary local storage: incidents are lost when the backend restarts or reloads."
          : "Storage status is unavailable. Check backend connectivity before creating incidents."}</p>
        <div className="mt-10 rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="text-sm text-slate-400">Backend connectivity</h2>
          <p role="status" className={`mt-2 text-lg ${status === "ready" ? "text-teal-400" : "text-amber-300"}`}>{label}</p>
          <p className="mt-3 text-sm text-slate-400">Refresh this page to check again.</p>
        </div>
        <IncidentWorkspace />
      </section>
      <footer className="text-sm text-slate-500">Phase 0 + Phase 1 foundation · Local development</footer>
    </main>
  );
}
