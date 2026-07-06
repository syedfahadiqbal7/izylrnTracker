import { Check, Languages } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cn } from "@/lib/utils";

/** Language picker (topbar). Switching re-fetches the bundle and flips RTL for Arabic. */
export function LanguageSwitcher() {
  const { locale, setLocale, locales, t } = useI18n();
  const active = locales.find((l) => l.code === locale);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2">
          <Languages className="size-4 text-muted-foreground" />
          <span className="hidden sm:inline">{active?.native_name ?? locale.toUpperCase()}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel>{t("app.language")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {locales.map((l) => (
          <DropdownMenuItem
            key={l.code}
            onClick={() => setLocale(l.code)}
            className="flex items-center justify-between gap-2"
          >
            <span className="flex flex-col">
              <span className={cn(l.rtl && "text-right")}>{l.native_name}</span>
              <span className="text-xs text-muted-foreground">{l.name}</span>
            </span>
            {l.code === locale && <Check className="size-4 text-brand-cyan" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
