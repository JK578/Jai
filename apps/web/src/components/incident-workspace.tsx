"use client";

import { useEffect, useState } from "react";
import { fetchIncident, fetchIncidents, type Incident } from "../lib/incidents";
import CreateIncidentForm from "./create-incident-form";

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Request failed. Please retry.";
}

function IncidentDetails({ id }: { id: string }) {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchIncident(id, controller.signal).then((item) => {
      if (!controller.signal.aborted) setIncident(item);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(cause));
    });
    return () => controller.abort();
  }, [id, attempt]);

  return <section aria-label="Incident details" className="rounded-xl border border-slate-800 bg-slate-900 p-6">
    <h2 className="text-xl font-semibold">Incident details</h2>
    {error ? <><p role="alert" className="mt-4 text-amber-300">{error}</p><button className="mt-3 underline" onClick={() => { setError(null); setIncident(null); setAttempt(attempt + 1); }}>Retry details</button></>
      : !incident ? <p role="status" className="mt-4">Loading incident details…</p>
      : <dl className="mt-4 space-y-3 break-words">
        {Object.entries({ Title: incident.title, Description: incident.description, Severity: incident.severity, Status: incident.status, Service: incident.service_name, ID: incident.id, Created: incident.created_at, Updated: incident.updated_at }).map(([label, value]) => <div key={label}><dt className="text-sm text-slate-400">{label}</dt><dd className="whitespace-pre-wrap">{value}</dd></div>)}
      </dl>}
  </section>;
}

export default function IncidentWorkspace() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchIncidents(controller.signal).then((items) => {
      if (!controller.signal.aborted) { setIncidents(items); setLoading(false); }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) { setError(errorMessage(cause)); setLoading(false); }
    });
    return () => controller.abort();
  }, [attempt]);

  return <div className="mt-8 grid items-start gap-6 lg:grid-cols-2">
    <div className="space-y-6">
      <section aria-label="Incident list" className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <div className="flex items-center justify-between gap-4"><h2 className="text-xl font-semibold">Incidents</h2><button disabled={loading} className="text-sm text-teal-300 underline disabled:opacity-50" onClick={() => { setLoading(true); setError(null); setSelected(null); setAttempt(attempt + 1); }}>Refresh incidents</button></div>
        {loading ? <p role="status" className="mt-4">Loading incidents…</p>
          : error ? <p role="alert" className="mt-4 text-amber-300">{error}</p>
          : incidents.length === 0 ? <p className="mt-4 text-slate-400">No incidents yet. Create your first incident.</p>
          : <ul className="mt-4 divide-y divide-slate-800">{incidents.map((incident) => <li key={incident.id} className="py-4"><button onClick={() => setSelected(incident.id)} aria-pressed={selected === incident.id} className="text-left font-medium text-teal-300 underline break-words">{incident.title}</button><p className="mt-1 text-sm text-slate-400">{incident.service_name} · {incident.severity} · {incident.status}</p></li>)}</ul>}
      </section>
      {selected && <IncidentDetails key={selected} id={selected} />}
    </div>
    <CreateIncidentForm onCreated={(incident) => { setIncidents((items) => [incident, ...items.filter((item) => item.id !== incident.id)]); setSelected(incident.id); setError(null); setLoading(true); setAttempt((current) => current + 1); }} />
  </div>;
}
