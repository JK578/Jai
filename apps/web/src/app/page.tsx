import { getBackendHealth } from "../lib/backend";
import IncidentWorkspace from "../components/incident-workspace";
import SignIn, { SignOut } from "../components/sign-in";
import { cookies } from "next/headers";
import { authEnabled, cookieName, backendRequest } from "../lib/session";
import WorkspaceShell from "../components/workspace-shell";

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getBackendHealth();
  let scopes: string[] = [];
  if (authEnabled()) {
    const token = (await cookies()).get(cookieName)?.value;
    const session = await backendRequest("/api/v1/auth/session", "GET", token);
    if (!session.ok) return <main className="min-h-screen px-6 py-12"><SignIn /></main>;
    const identity = await session.json();
    scopes = Array.isArray(identity.scopes) ? identity.scopes : [];
  }
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
        <div className="flex items-center gap-5"><span className="text-sm text-slate-400">Development workspace</span>{authEnabled() && <SignOut />}</div>
      </header>
      <section className="py-10">
        <p className="mb-5 text-sm font-medium uppercase tracking-widest text-teal-400">Incident response</p>
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
        {authEnabled() ? <WorkspaceShell scopes={scopes} /> : <IncidentWorkspace />}
      </section>
      <footer className="text-sm text-slate-500">IncidentIQ · Local workspace</footer>
    </main>
  );
}
