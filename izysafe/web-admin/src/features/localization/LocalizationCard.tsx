import { useMemo, useState, type FormEvent } from "react";
import { Languages, Loader2, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useT } from "@/lib/i18n/I18nProvider";
import {
  useCreateTranslation,
  useDeleteTranslation,
  useTranslations,
  useUpdateTranslation,
  type TranslationRow,
} from "./api";

/** Admin localization editor: every translation key across en / hi / ar, searchable,
 *  with add / edit / delete. Saving refreshes the live panel bundle. */
export function LocalizationCard() {
  const t = useT();
  const query = useTranslations();
  const [search, setSearch] = useState("");
  const [editRow, setEditRow] = useState<TranslationRow | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);
  const del = useDeleteTranslation();

  const rows = useMemo(() => {
    const all = query.data ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (r) =>
        r.key.toLowerCase().includes(q) ||
        r.en.toLowerCase().includes(q) ||
        (r.hi ?? "").toLowerCase().includes(q) ||
        (r.ar ?? "").toLowerCase().includes(q),
    );
  }, [query.data, search]);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Languages className="size-5" />
            {t("settings.localization", "Localization")}
          </CardTitle>
          <CardDescription>
            {t(
              "settings.localization_desc",
              "Manage translations for every language. Changes apply across the panel.",
            )}
          </CardDescription>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" />
          {t("localization.add_key", "Add key")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder={t("common.search", "Search") + "…"}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {query.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : (
          <div className="max-h-[28rem] overflow-y-auto rounded-md border">
            <Table>
              <TableHeader className="sticky top-0 bg-background">
                <TableRow>
                  <TableHead className="w-[26%]">{t("localization.key", "Key")}</TableHead>
                  <TableHead>English</TableHead>
                  <TableHead>हिन्दी</TableHead>
                  <TableHead>العربية</TableHead>
                  <TableHead className="w-[80px] text-right">
                    {t("common.actions", "Actions")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.key}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {r.key}
                    </TableCell>
                    <TableCell>{r.en}</TableCell>
                    <TableCell>{r.hi ?? <Missing />}</TableCell>
                    <TableCell dir="rtl">{r.ar ?? <Missing />}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" onClick={() => setEditRow(r)}>
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setDeleteKey(r.key)}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      No translations match “{search}”.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>

      {editRow && <EditDialog row={editRow} onClose={() => setEditRow(null)} />}
      {addOpen && <AddDialog onClose={() => setAddOpen(false)} />}
      <ConfirmDialog
        open={deleteKey !== null}
        onOpenChange={(o) => !o && setDeleteKey(null)}
        title="Delete translation"
        description={
          <>
            Delete <span className="font-mono">{deleteKey}</span>? Any UI using this key
            will fall back to the key name.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={() => del.mutateAsync(deleteKey!).then(() => setDeleteKey(null))}
      />
    </Card>
  );
}

function Missing() {
  return <span className="text-xs italic text-muted-foreground/60">not set</span>;
}

function EditDialog({ row, onClose }: { row: TranslationRow; onClose: () => void }) {
  const update = useUpdateTranslation();
  const [en, setEn] = useState(row.en);
  const [hi, setHi] = useState(row.hi ?? "");
  const [ar, setAr] = useState(row.ar ?? "");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await update.mutateAsync({ key: row.key, en, hi: hi || null, ar: ar || null });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle className="font-mono text-base">{row.key}</DialogTitle>
            <DialogDescription>Edit this string in each language.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Field label="English" value={en} onChange={setEn} required />
            <Field label="हिन्दी (Hindi)" value={hi} onChange={setHi} />
            <Field label="العربية (Arabic)" value={ar} onChange={setAr} rtl />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={update.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending || !en.trim()}>
              {update.isPending && <Loader2 className="size-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function AddDialog({ onClose }: { onClose: () => void }) {
  const create = useCreateTranslation();
  const [key, setKey] = useState("");
  const [en, setEn] = useState("");
  const [hi, setHi] = useState("");
  const [ar, setAr] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!/^[a-zA-Z0-9._-]+$/.test(key)) {
      setError("Key may contain only letters, numbers, dots, dashes and underscores.");
      return;
    }
    try {
      await create.mutateAsync({ key, en, hi: hi || null, ar: ar || null });
      onClose();
    } catch {
      /* toast handled globally */
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Add translation key</DialogTitle>
            <DialogDescription>
              Use a dotted namespace, e.g. <span className="font-mono">nav.reports</span>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="tr-key">Key</Label>
              <Input
                id="tr-key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="section.name"
                className="font-mono"
                required
              />
            </div>
            <Field label="English" value={en} onChange={setEn} required />
            <Field label="हिन्दी (Hindi)" value={hi} onChange={setHi} />
            <Field label="العربية (Arabic)" value={ar} onChange={setAr} rtl />
            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={create.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || !key.trim() || !en.trim()}>
              {create.isPending && <Loader2 className="size-4 animate-spin" />}
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
  rtl,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  rtl?: boolean;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        dir={rtl ? "rtl" : "ltr"}
      />
    </div>
  );
}

/** Full-page wrapper (kept here so Settings can embed the card and a future route can
 *  reuse it). Currently embedded in Settings. */
export function LocalizationSection() {
  const t = useT();
  return (
    <>
      <PageHeader title={t("settings.localization", "Localization")} />
      <LocalizationCard />
    </>
  );
}
