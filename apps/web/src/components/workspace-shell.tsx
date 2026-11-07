"use client";
import { useState } from "react";
import IncidentWorkspace from "./incident-workspace";
import EvidenceWorkspace from "./evidence-workspace";
import InvestigationWorkspace from "./investigation-workspace";

export default function WorkspaceShell({ scopes }: { scopes: string[] }) {
  const [tab, setTab] = useState("Incidents");
  return <div><nav aria-label="Workspace sections" className="mt-8 flex flex-wrap gap-2 border-b border-slate-700 pb-3">
    {["Incidents", "Logs & search", "Investigations"].map(name => <button key={name} aria-current={tab === name ? "page" : undefined} onClick={() => setTab(name)}
      className={`rounded px-4 py-3 text-sm font-semibold ${tab === name ? "bg-teal-400 text-slate-950" : "text-slate-300 hover:bg-slate-800"}`}>{name}</button>)}
  </nav>{tab === "Incidents" && <IncidentWorkspace />}{tab === "Logs & search" && <EvidenceWorkspace canSearch={scopes.includes("search:run")} />}
    {tab === "Investigations" && <InvestigationWorkspace scopes={scopes} />}</div>;
}
