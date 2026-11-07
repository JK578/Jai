"use client";
import { useEffect, useState } from "react";
import { workspaceRequest } from "../lib/workspace";

type Log = { id: string; event_id?: string; source_line: number; message?: string; text?: string;
  normalized_level?: string; source_time_text?: string; raw_line?: string; file_id?: string };
type Page = { items: Log[]; next_cursor?: number | null };

export default function EvidenceWorkspace({ canSearch }: { canSearch: boolean }) {
  const [file, setFile] = useState("");
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Log[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [selected, setSelected] = useState<Log | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const catalog = await workspaceRequest<{ items: { file_id: string; name: string }[] }>("log-datasets");
        if (!active) return;
        if (catalog.items.length) {
          const item = catalog.items[0]; setFile(item.file_id); setName(item.name);
          const page = await workspaceRequest<Page>(`logs?file_id=${item.file_id}&limit=20`);
          if (active) { setRows(page.items); setNext(page.next_cursor ?? null); }
        }
      } catch (e) { if (active) setError((e as Error).message); }
      finally { if (active) setReady(true); }
    })();
    return () => { active = false; };
  }, []);
  async function search(semantic = false, cursor = 0) {
    setBusy(true); setError(""); setSelected(null);
    try {
      const page = semantic
        ? await workspaceRequest<Page>("search", { question: query })
        : await workspaceRequest<Page>(`logs?file_id=${file}&limit=20&cursor=${cursor}${query ? `&q=${encodeURIComponent(query)}` : ""}`);
      setRows(cursor ? previous => [...previous, ...page.items] : page.items);
      setNext(page.next_cursor ?? null);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="mt-8 space-y-5" aria-label="Log evidence">
    <div><h2 className="text-2xl font-semibold">Explore log evidence</h2><p className="mt-2 text-sm text-slate-400">{name || (ready ? "No source files assigned to your workspace." : "Loading source files…")}</p></div>
    {file && <form className="flex flex-wrap items-end gap-3" onSubmit={e => { e.preventDefault(); void search(); }}>
      <label className="min-w-56 flex-1 text-sm">Find log messages
        <input value={query} maxLength={200} onChange={e => setQuery(e.target.value)} placeholder="Words or phrases in the source"
          className="mt-2 w-full rounded border border-slate-600 bg-slate-950 p-3" />
      </label>
      <button disabled={busy} className="rounded bg-teal-400 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50">Find text</button>
      {canSearch && <button type="button" disabled={busy || !query.trim()} onClick={() => void search(true)} className="rounded border border-teal-500 px-4 py-3 text-teal-200 disabled:opacity-50">Semantic search</button>}
      {canSearch && <p className="w-full text-xs text-slate-400">Semantic search uses a small embedding request within your daily model budget.</p>}
    </form>}
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {busy && <p role="status" className="text-slate-300">Searching evidence…</p>}
    {ready && file && !rows.length && !busy && <p>No matching log events.</p>}
    <div className="grid gap-5 lg:grid-cols-2">
      <ol className="space-y-2">{rows.map(row => <li key={row.id ?? row.event_id}>
        <button className="w-full rounded border border-slate-700 bg-slate-900 p-4 text-left hover:border-teal-500"
          onClick={async () => { try { setError(""); setSelected(await workspaceRequest<Log>(`logs/${row.id ?? row.event_id}`)); } catch (e) { setError((e as Error).message); } }}>
          <span className="text-xs text-teal-300">Line {row.source_line}{row.normalized_level ? ` · ${row.normalized_level}` : ""}</span>
          <p className="mt-2 break-words text-sm">{row.message ?? row.text}</p>
        </button>
      </li>)}</ol>
      {selected && <article className="self-start rounded-xl border border-slate-700 p-5" aria-label="Source log detail">
        <h3 className="font-semibold">Source line {selected.source_line}</h3>
        <p className="mt-2 text-xs text-slate-400">{selected.source_time_text} · Source timezone unknown</p>
        <pre className="mt-4 whitespace-pre-wrap break-words text-sm">{selected.raw_line ?? selected.message}</pre>
      </article>}
    </div>
    {next !== null && <button disabled={busy} onClick={() => void search(false, next)} className="rounded border border-slate-600 px-4 py-2">Load more events</button>}
  </section>;
}
