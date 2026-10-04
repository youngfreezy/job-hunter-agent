"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { modelSettings, type ModelSettings } from "@/lib/model-settings";

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
  return <Card id="model-keys"><CardHeader><CardTitle>Model API key</CardTitle><CardDescription>Bring your Anthropic key for AI coaching and browser actions. Your key is encrypted and never displayed again. Anthropic and Browserbase bill usage to your own accounts; application credits are separate.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      {settings?.server_credentials_available && <p className="text-sm text-muted-foreground">Your account can use the configured demo model credentials.</p>}
      <label className="block space-y-1 text-sm"><span>Anthropic API key</span><input type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => { setKey(e.target.value); setSaved(false); }} placeholder={settings?.anthropic_key_set ? `Saved (${settings.anthropic_key_hint || "hidden"})` : "sk-ant-…"} className="w-full rounded-md border bg-background px-3 py-2" disabled={busy} /></label>
      <div className="flex flex-wrap gap-2"><Button disabled={busy || !key.trim()} onClick={() => save(key.trim())}>{busy ? "Saving…" : "Save model key"}</Button>{settings?.anthropic_key_set && <Button variant="outline" disabled={busy} onClick={() => save("")}>Remove saved key</Button>}</div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {saved && <p role="status" className="text-sm">Model settings saved. Saving does not make a model request.</p>}
      <p className="text-xs text-muted-foreground">Next, add your Browserbase key and project below, then connect your Indeed login.</p>
    </CardContent></Card>;
}
