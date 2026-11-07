"use client";
import { useState } from "react";

export default function SignIn() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <section className="mx-auto mt-12 w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-8">
    <h1 className="text-2xl font-semibold">Sign in to IncidentIQ</h1>
    <p className="mt-3 text-sm text-slate-300">Use the access token provided by your workspace administrator.</p>
    <form className="mt-6 space-y-4" onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError("");
      try {
        const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
        if (!response.ok) throw new Error("Sign-in failed. Check your access token.");
        setToken(""); window.location.reload();
      } catch { setError("Sign-in failed. Check your access token and try again."); }
      finally { setBusy(false); }
    }}>
      <label className="block text-sm">Access token
        <input type="password" autoComplete="current-password" required maxLength={256} value={token}
          onChange={e => setToken(e.target.value)} className="mt-2 w-full rounded border border-slate-600 bg-slate-950 p-3" />
      </label>
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      <button disabled={busy} className="rounded bg-teal-400 px-5 py-3 font-semibold text-slate-950 disabled:opacity-50">{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </section>;
}

export function SignOut() {
  return <button className="text-sm text-slate-300 underline" onClick={async () => {
    await fetch("/api/auth/logout", { method: "POST" }); window.location.reload();
  }}>Sign out</button>;
}
