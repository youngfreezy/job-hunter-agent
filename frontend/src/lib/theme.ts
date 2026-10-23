// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "jh-theme";

const ORDER: ThemePreference[] = ["system", "light", "dark"];

export function parseThemePreference(value: unknown): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export function nextThemePreference(current: ThemePreference): ThemePreference {
  return ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
}

export function resolveDark(pref: ThemePreference, systemPrefersDark: boolean): boolean {
  return pref === "dark" || (pref === "system" && systemPrefersDark);
}

/**
 * Runs in <head> before first paint so there is no flash of the wrong theme.
 * Keep in sync with resolveDark(); it cannot import modules.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k=${JSON.stringify(THEME_STORAGE_KEY)};var m=window.matchMedia("(prefers-color-scheme: dark)");var p=function(){var v=null;try{v=localStorage.getItem(k)}catch(e){}return v==="light"||v==="dark"?v:"system"};var a=function(){var v=p();document.documentElement.classList.toggle("dark",v==="dark"||(v==="system"&&m.matches))};a();m.addEventListener("change",a);window.addEventListener("storage",function(e){if(e.key===k)a()})}catch(e){}})();`;

export function readThemePreference(): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

export function applyThemePreference(pref: ThemePreference): void {
  try {
    if (pref === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // Storage blocked (private mode etc.) — still apply for this page view.
  }
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", resolveDark(pref, systemDark));
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: pref }));
}

export const THEME_CHANGE_EVENT = "jh-theme-change";
