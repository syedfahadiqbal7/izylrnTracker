import { Construction } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { Card, CardContent } from "@/components/ui/card";

/** Stub for pages that will be built out page-by-page in later slices. */
export function PlaceholderPage({
  title,
  description,
  planned,
}: {
  title: string;
  description?: string;
  planned?: string;
}) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <Construction className="size-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            {planned ?? "This page is coming soon."}
          </p>
        </CardContent>
      </Card>
    </>
  );
}
