/**
 * App-wide localization. Loads the active locale's bundle from the backend
 * (GET /i18n/{locale}) and exposes `t(key, fallback?)`. No UI string is hard-coded —
 * components pull every label through `t`, and admins edit the bundles from the panel.
 *
 * The active locale is persisted in localStorage and applied to <html lang/dir> so
 * Arabic flips the whole panel to RTL.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchBundle, fetchLocales } from "./api";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  type Locale,
  type LocaleMeta,
  type TranslationBundle,
} from "./types";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Translate a key; falls back to the provided text, then the key itself. */
  t: (key: string, fallback?: string) => string;
  locales: LocaleMeta[];
  isRTL: boolean;
  ready: boolean;
}

const I18nContext = createContext<I18nContextValue | null>(null);

const FALLBACK_LOCALES: LocaleMeta[] = [
  { code: "en", name: "English", native_name: "English", rtl: false },
  { code: "hi", name: "Hindi", native_name: "हिन्दी", rtl: false },
  { code: "ar", name: "Arabic", native_name: "العربية", rtl: true },
];

function readStoredLocale(): Locale {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored === "en" || stored === "hi" || stored === "ar") return stored;
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  const localesQuery = useQuery({
    queryKey: ["i18n", "locales"],
    queryFn: fetchLocales,
    staleTime: Infinity,
  });

  const bundleQuery = useQuery<TranslationBundle>({
    queryKey: ["i18n", "bundle", locale],
    queryFn: () => fetchBundle(locale),
    staleTime: 5 * 60_000,
    // Keep showing the previous language's strings while the next bundle loads.
    placeholderData: (prev) => prev,
  });

  const locales = localesQuery.data ?? FALLBACK_LOCALES;
  const isRTL = locales.find((l) => l.code === locale)?.rtl ?? false;

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem(LOCALE_STORAGE_KEY, next);
    setLocaleState(next);
  }, []);

  // Reflect the language + direction on the document root.
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = isRTL ? "rtl" : "ltr";
  }, [locale, isRTL]);

  const bundle = bundleQuery.data;
  const t = useCallback(
    (key: string, fallback?: string) => bundle?.[key] ?? fallback ?? key,
    [bundle],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t, locales, isRTL, ready: bundleQuery.isSuccess }),
    [locale, setLocale, t, locales, isRTL, bundleQuery.isSuccess],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

/** Convenience: just the translate function. */
export function useT(): I18nContextValue["t"] {
  return useI18n().t;
}
