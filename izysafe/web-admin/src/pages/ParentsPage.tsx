import { useEffect, useMemo, useState, type FormEvent } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  Loader2,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
  UsersRound,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { useT } from "@/lib/i18n/I18nProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { ApiClientError } from "@/types/api";
import {
  useParents,
  useRemoveParent,
  useUpdateParent,
  type Parent,
} from "@/features/parents/api";

const PAGE_SIZE = 20;

export function ParentsPage() {
  const t = useT();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search.trim(), 300);
  const [page, setPage] = useState(0);
  const [editFor, setEditFor] = useState<Parent | null>(null);
  const [removeFor, setRemoveFor] = useState<Parent | null>(null);

  useEffect(() => setPage(0), [q]);

  const params = useMemo(
    () => ({ q: q || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }),
    [q, page],
  );
  const parents = useParents(params);
  const rows = parents.data?.items ?? [];
  const total = parents.data?.meta?.total ?? 0;
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);

  return (
    <>
      <PageHeader
        title={t("parents.title", "Parents")}
        description={t("parents.desc", "Parents of your enrolled students. Removing a parent from the school revokes their app access.")}
      />

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="space-y-2">
            <Label>{t("common.search", "Search")}</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("parents.search", "Name or phone…")}
                className="w-72 pl-8"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {parents.isError && (
        <Card>
          <CardContent className="py-12 text-center text-sm font-medium text-destructive">
            {parents.error instanceof ApiClientError
              ? parents.error.message
              : t("parents.load_error", "Failed to load parents.")}
          </CardContent>
        </Card>
      )}

      {parents.isLoading && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </CardContent>
        </Card>
      )}

      {parents.isSuccess && (
        <Card>
          <CardContent className="pt-6">
            {rows.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-14 text-center">
                <UsersRound className="size-9 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {q
                    ? t("roster.no_match", "No matches.")
                    : t("parents.empty", "No parents yet.")}
                </p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("parents.parent", "Parent")}</TableHead>
                      <TableHead>{t("parents.phone", "Phone")}</TableHead>
                      <TableHead>{t("parents.students", "Students")}</TableHead>
                      <TableHead>{t("parents.last_login", "Last sign-in")}</TableHead>
                      <TableHead className="text-right">{t("common.actions", "Actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell className="font-medium">
                          {p.name ?? (
                            <span className="italic text-muted-foreground">
                              {t("parents.no_name", "No name set")}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="tabular-nums text-muted-foreground">
                          {p.phone}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {p.children.map((c, i) => (
                              <Badge key={i} variant="secondary">
                                {c.name}
                                {c.class_grade ? ` · ${c.class_grade}` : ""}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {p.last_login_at
                            ? formatDistanceToNow(new Date(p.last_login_at), { addSuffix: true })
                            : t("parents.never", "Never")}
                        </TableCell>
                        <TableCell className="text-right">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon">
                                <MoreHorizontal className="size-4" />
                                <span className="sr-only">{t("roster.open_actions", "Open actions")}</span>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setEditFor(p)}>
                                <Pencil className="size-4" />
                                {t("parents.edit_name", "Edit name")}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() => setRemoveFor(p)}
                              >
                                <Trash2 className="size-4" />
                                {t("parents.remove", "Remove from school")}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="mt-4 flex items-center justify-between">
                  <p className="text-sm text-muted-foreground">
                    {from}–{to} {t("roster.of", "of")} {total}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page === 0 || parents.isFetching}
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                    >
                      {t("roster.previous", "Previous")}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={to >= total || parents.isFetching}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      {t("roster.next", "Next")}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <EditNameDialog parent={editFor} onClose={() => setEditFor(null)} />
      <RemoveParentDialog parent={removeFor} onClose={() => setRemoveFor(null)} />
    </>
  );
}

function EditNameDialog({ parent, onClose }: { parent: Parent | null; onClose: () => void }) {
  const t = useT();
  const update = useUpdateParent();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [seededFor, setSeededFor] = useState<string | null>(null);
  if (parent && seededFor !== parent.id) {
    setSeededFor(parent.id);
    setName(parent.name ?? "");
    setError(null);
    update.reset();
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!parent) return;
    setError(null);
    try {
      await update.mutateAsync({ id: parent.id, name: name.trim() || null });
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("parents.save_error", "Could not save the change."),
      );
    }
  };

  return (
    <Dialog open={parent !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{t("parents.edit_name", "Edit name")}</DialogTitle>
            <DialogDescription>{parent?.phone}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="p-name">{t("parents.parent", "Parent")}</Label>
            <Input
              id="p-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("child.name_hint", "e.g. Ahmed")}
            />
            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={update.isPending}>
              {t("common.cancel", "Cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending && <Loader2 className="size-4 animate-spin" />}
              {t("common.save", "Save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RemoveParentDialog({ parent, onClose }: { parent: Parent | null; onClose: () => void }) {
  const t = useT();
  const remove = useRemoveParent();
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    if (!parent) return;
    setError(null);
    try {
      await remove.mutateAsync(parent.id);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("parents.remove_error", "Could not remove the parent."),
      );
    }
  };

  return (
    <Dialog open={parent !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("parents.remove_title", "Remove parent")}</DialogTitle>
          <DialogDescription>
            {t("parents.remove_desc", "Remove this parent and their students from the school? Their app access is revoked once they have no active enrollment. History is kept.")}
          </DialogDescription>
        </DialogHeader>
        {parent && (
          <p className="text-sm">
            <span className="font-medium">{parent.name ?? parent.phone}</span>
            {parent.child_count > 0 && (
              <span className="text-muted-foreground">
                {" "}· {parent.child_count} {t("parents.students", "Students").toLowerCase()}
              </span>
            )}
          </p>
        )}
        {error && <p className="text-sm font-medium text-destructive">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={remove.isPending}>
            {t("common.cancel", "Cancel")}
          </Button>
          <Button variant="destructive" onClick={confirm} disabled={remove.isPending}>
            {remove.isPending && <Loader2 className="size-4 animate-spin" />}
            {t("parents.remove", "Remove from school")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
