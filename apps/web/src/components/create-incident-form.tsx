"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { createIncident, severities, type Incident } from "../lib/incidents";

export default function CreateIncidentForm({ onCreated }: { onCreated: (incident: Incident) => void }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    submitting.current = true;
    setPending(true);
    setError(null);
    try {
      const incident = await createIncident({
        title: String(data.get("title") ?? ""), description: String(data.get("description") ?? ""),
        service_name: String(data.get("service_name") ?? ""), severity: String(data.get("severity") ?? ""),
      });
      onCreated(incident);
      form.reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create incident.");
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  const inputClass = "mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-100";
  return (
    <form onSubmit={submit} noValidate aria-label="Create incident" className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
      <h2 className="text-xl font-semibold">Create incident</h2>
      <fieldset disabled={pending} className="space-y-4">
        <label className="block">Title<input className={inputClass} name="title" required maxLength={200} /></label>
        <label className="block">Description<textarea className={inputClass} name="description" required maxLength={10000} rows={4} /></label>
        <label className="block">Service name<input className={inputClass} name="service_name" required maxLength={100} /></label>
        <label className="block">Severity<select className={inputClass} name="severity" defaultValue="medium">{severities.map((severity) => <option key={severity} value={severity}>{severity}</option>)}</select></label>
        <p className="text-sm text-slate-400">New incidents start with status open. All fields are required.</p>
        {error && <p role="alert" className="text-amber-300">{error}</p>}
        <button type="submit" className="rounded-lg bg-teal-400 px-5 py-3 font-semibold text-slate-950 disabled:opacity-50">{pending ? "Creating…" : "Create incident"}</button>
      </fieldset>
    </form>
  );
}
