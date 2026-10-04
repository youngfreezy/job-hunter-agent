"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { modelBudgetAmount, modelSettings, type ModelSettings } from "@/lib/model-settings";

export function ModelSettingsCard() {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => { modelSettings().then(setSettings).catch((e) => setError(e.message)); }, []);
  async function save(value: string) {
    setBusy(true); setError(""); setSaved(false);
    try { setSettings(await modelSettings(value)); setKey(""); setSaved(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save key."); }
    finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true);
    setError("");
    try { setSettings(await modelSettings()); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not refresh settings."); }
    finally { setBusy(false); }
  }
  return <Card id="model-keys"><CardHeader><CardTitle>Model API key</CardTitle><CardDescription>Bring your Anthropic key for AI coaching and browser actions. Your key is encrypted and never displayed again. Anthropic and Browserbase bill usage to your own accounts; application credits are separate.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      {settings?.server_credentials_available && <p className="text-sm text-muted-foreground">Your account can use the configured demo model credentials.</p>}
      {settings?.models && <section aria-label="Effective models" className="rounded-lg border p-4 space-y-3">
        <h3 className="text-sm font-medium">Effective models</h3>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          {([['default', 'Standard tasks'], ['premium', 'Premium tasks'], ['light', 'Lightweight tasks'], ['browser', 'Browser actions']] as const).map(([role, label]) =>
            <div key={role}><dt className="text-muted-foreground">{label}</dt><dd className="break-all font-mono text-xs">{settings.models?.[role]}</dd></div>
          )}
        </dl>
      </section>}
      {settings?.funding === 'server_demo' && settings.budget && <section aria-label="Demo model allowance" className="rounded-lg border p-4 space-y-3">
        <h3 className="text-sm font-medium">Demo model allowance</h3>
        {settings.budget.status === 'available' ? <>
          <p className="text-lg font-semibold">{modelBudgetAmount(settings.budget.remaining)} uncommitted</p>
          <dl className="grid gap-2 text-sm sm:grid-cols-3">
            <div><dt className="text-muted-foreground">Model cap</dt><dd>{modelBudgetAmount(settings.budget.cap)}</dd></div>
            <div><dt className="text-muted-foreground">Settled usage</dt><dd>{modelBudgetAmount(settings.budget.settled)}</dd></div>
            <div><dt className="text-muted-foreground">Reserved / unresolved</dt><dd>{modelBudgetAmount(settings.budget.reserved)}</dd></div>
          </dl>
          <p className="text-xs text-muted-foreground">Remaining allowance excludes unsettled reservations. Reservations are not confirmed charges. This guard covers model requests sharing the demo ledger; Browserbase is billed separately.</p>
        </> : <p className="text-sm text-muted-foreground">{settings.budget.status === 'unavailable' ? 'The model allowance could not be read. Demo model requests are blocked until it is available.' : 'No demo model allowance is configured.'}</p>}
      </section>}
      <Button type="button" variant="outline" disabled={busy} onClick={refresh}>Refresh model status</Button>
      <label className="block space-y-1 text-sm"><span>Anthropic API key</span><input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => { setKey(e.target.value); setSaved(false); }} placeholder={settings?.anthropic_key_set ? `Saved (${settings.anthropic_key_hint || "hidden"})` : "sk-ant-…"} className="w-full rounded-md border bg-background px-3 py-2" disabled={busy} /></label>
      <div className="flex flex-wrap gap-2"><Button disabled={busy || !key.trim()} onClick={() => save(key.trim())}>{busy ? "Saving…" : "Save model key"}</Button>{settings?.anthropic_key_set && <Button variant="outline" disabled={busy} onClick={() => save("")}>Remove saved key</Button>}</div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {saved && <p role="status" className="text-sm">Model settings saved. Saving does not make a model request.</p>}
      <p className="text-xs text-muted-foreground">Next, add your Browserbase key and project below, then connect your Indeed login.</p>
    </CardContent></Card>;
}
