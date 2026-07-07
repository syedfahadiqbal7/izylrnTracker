import { Link } from "react-router-dom";
import { useT } from "@/lib/i18n/I18nProvider";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const t = useT();
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <p className="text-4xl font-semibold">404</p>
      <p className="text-muted-foreground">{t("notfound.message", "This page could not be found.")}</p>
      <Button asChild variant="outline">
        <Link to="/">{t("notfound.back", "Back to dashboard")}</Link>
      </Button>
    </div>
  );
}
