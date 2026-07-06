/** Supported UI languages. Kept in sync with the backend `translations` columns. */
export type Locale = "en" | "hi" | "ar";

export interface LocaleMeta {
  code: Locale;
  name: string;
  native_name: string;
  rtl: boolean;
}

/** A loaded translation bundle: { "nav.dashboard": "Dashboard", ... }. */
export type TranslationBundle = Record<string, string>;

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_STORAGE_KEY = "izylrn.locale";
