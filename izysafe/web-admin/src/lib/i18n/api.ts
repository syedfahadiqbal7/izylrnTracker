import { apiGet } from "@/lib/api";
import type { Locale, LocaleMeta, TranslationBundle } from "./types";

/** Supported languages (public — no auth). */
export function fetchLocales(): Promise<LocaleMeta[]> {
  return apiGet<LocaleMeta[]>("/i18n/locales");
}

/** The full {key: value} bundle for a locale (public, English-fallback filled). */
export function fetchBundle(locale: Locale): Promise<TranslationBundle> {
  return apiGet<TranslationBundle>(`/i18n/${locale}`);
}
