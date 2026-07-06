import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/I18nProvider";

/**
 * Light/dark theme toggle. Flips the `dark` class on <html> (Tailwind `darkMode: class`,
 * shadcn CSS-var theming does the rest) and persists the choice in localStorage. The
 * initial class is applied pre-render by the inline script in index.html (no flash).
 */
const THEME_KEY = "izylrn.theme";

function isDark(): boolean {
  return document.documentElement.classList.contains("dark");
}

export function ThemeToggle() {
  const t = useT();
  const [dark, setDark] = useState(isDark);

  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    setDark(next);
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={t("app.toggle_theme", "Toggle theme")}
      title={t("app.toggle_theme", "Toggle theme")}
    >
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}
