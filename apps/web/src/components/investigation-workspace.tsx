"use client";
import { useCallback, useEffect, useState } from "react";
import { Investigation, workspaceRequest } from "../lib/workspace";

type Summary = Pick<Investigation, "run_id" | "question" | "status" | "provider">;

export default function InvestigationWorkspace({ scopes }: { scopes: string[] }) {
  const [question, setQuestion] = useState("");
  const [provider, setProvider] = useState<"mock" | "openai">("mock");
  const [current, setCurrent] = useState<Investigation | null>(null);
  const [history, setHistory] = useState<Summary[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refreshHistory = useCallback(async () => {
    try { setHistory((await workspaceRequest<{ items: Summary[] }>("investigations")).items); }
    catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => {
    let active = true;
    workspaceRequest<{ items: Summary[] }>("investigations")
      .then(data => { if (active) setHistory(data.items); })
      .catch(e => { if (active) setError((e as Error).message); });
    return () => { active = false; };
  }, []);
  async function act(action?: string) {
    setError(""); setBusy(true);
    try {
      if (!action && new TextEncoder().encode(question).length > 800) throw new Error("Please shorten your question.");
      const path = action ? `investigations/${current!.run_id}/${action}` : "investigations";
      const body = action ? { report_sha256: current!.report_sha256 } : { question, provider };
      setCurrent(await workspaceRequest<Investigation>(path, body));
      await refreshHistory();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="mt-8 space-y-6" aria-label="Investigations">
    <div><h2 className="text-2xl font-semibold">Investigate with evidence</h2><p className="mt-2 text-sm text-slate-400">Build a cited draft, review its limits, and decide whether to save it.</p></div>
    <form className="space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-5" onSubmit={e => { e.preventDefault(); void act(); }}>
      <label className="block text-sm">Investigation question<textarea required maxLength={800} value={question}
        onChange={e => setQuestion(e.target.value)} rows={3} className="mt-2 w-full rounded border border-slate-600 bg-slate-950 p-3" /></label>
      <label className="block text-sm">Investigation mode<select value={provider} onChange={e => setProvider(e.target.value as "mock" | "openai")}
        className="ml-3 rounded border border-slate-600 bg-slate-950 p-2"><option value="mock">Demo · no credits</option><option value="openai">Live AI · up to $0.02 per run</option></select></label>
      <button disabled={busy || !question.trim() || !scopes.includes("investigations:write")}
        className="rounded bg-teal-400 px-5 py-3 font-semibold text-slate-950 disabled:opacity-50">{busy ? "Preparing investigation…" : "Start investigation"}</button>
    </form>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {current && <article className="space-y-5 rounded-xl border border-slate-700 p-6" aria-label="Investigation report">
      <div className="flex flex-wrap justify-between gap-3"><h3 className="text-xl font-semibold">{current.question}</h3><span role="status" className="text-sm text-teal-300">{current.status.replaceAll("_", " ")}</span></div>
      {current.provider === "mock" && <p className="text-sm text-amber-200">Demo report using synthetic evidence. No model inference performed.</p>}
      {current.report && <>
        <p className="text-slate-200">{current.report.summary}</p>
        <div><h4 className="font-semibold">Findings</h4><ul className="mt-2 space-y-3">{current.report.findings.map((finding, i) => <li key={i} className="border-l-2 border-teal-600 pl-4">
          <p>{finding.claim}</p><div className="mt-2 flex flex-wrap gap-3">{finding.evidence_ids.map(id => {
            const source = current.evidence.find(item => item.event_id === id);
            return <a key={id} className="text-sm text-teal-300 underline" href={`#source-${id}`}>Source line {source?.source_line ?? "unknown"}</a>;
          })}</div></li>)}</ul></div>
        <div><h4 className="font-semibold text-amber-200">Uncertainties</h4><ul className="mt-2 list-inside list-disc space-y-2 text-slate-300">{current.report.uncertainties.map((text, i) => <li key={i}>{text}</li>)}</ul></div>
        <div><h4 className="font-semibold">Suggested next steps</h4><ul className="mt-2 list-inside list-disc space-y-2 text-slate-300">{current.report.next_steps.map((text, i) => <li key={i}>{text}</li>)}</ul><p className="mt-3 text-xs text-slate-400">Suggestions are for review. IncidentIQ does not execute operational commands.</p></div>
        <details><summary className="cursor-pointer font-semibold">Source evidence ({current.evidence.length})</summary><div className="mt-4 space-y-3">{current.evidence.map(item => <div id={`source-${item.event_id}`} key={item.event_id} className="rounded bg-slate-900 p-4">
          <p className="text-xs text-teal-300">{item.source_path} · line {item.source_line}</p><p className="mt-2 whitespace-pre-wrap break-words text-sm">{item.text}</p>
        </div>)}</div></details>
      </>}
      {current.status === "awaiting_approval" && <div className="space-y-3 border-t border-slate-700 pt-5"><p className="text-sm text-slate-300">Review the claims and source evidence before approving this draft.</p>
        <div className="flex gap-3"><button disabled={busy || !scopes.includes("investigations:approve")} onClick={() => void act("approve")} className="rounded bg-teal-400 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50">Approve &amp; save report</button>
          <button disabled={busy || !scopes.includes("investigations:approve")} onClick={() => void act("reject")} className="rounded border border-slate-500 px-4 py-3 disabled:opacity-50">Reject draft</button></div></div>}
      {current.status === "failed" && <p className="text-amber-200">The investigation stopped safely. Review the question and try again later.</p>}
      {current.status === "failed" && current.attempt < 1 && <button disabled={busy} onClick={() => void act("retry")} className="rounded border border-slate-500 px-4 py-2">Retry once</button>}
      {current.status === "approved" && <button disabled={busy} onClick={() => void act("resume")} className="rounded border border-slate-500 px-4 py-2">Resume approved publication</button>}
      {current.published && <button className="rounded border border-teal-500 px-4 py-2 text-teal-200" onClick={() => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(current, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = `incidentiq-${current.run_id.slice(0, 8)}.json`; link.click(); URL.revokeObjectURL(url);
      }}>Download approved report</button>}
    </article>}
    <aside><h3 className="font-semibold">Your investigations</h3>{!history.length && <p className="mt-3 text-sm text-slate-400">Your new investigations will appear here.</p>}
      <ul className="mt-3 space-y-2">{history.map(item => <li key={item.run_id}><button disabled={busy} className="w-full rounded border border-slate-700 p-3 text-left hover:border-teal-500" onClick={async () => {
        setBusy(true); setError(""); try { setCurrent(await workspaceRequest<Investigation>(`investigations/${item.run_id}`)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
      }}><span className="block text-sm">{item.question}</span><span className="mt-1 block text-xs text-slate-400">{item.status.replaceAll("_", " ")}</span></button></li>)}</ul>
    </aside>
  </section>;
}
