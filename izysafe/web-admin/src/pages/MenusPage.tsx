import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  EyeOff,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { ConfirmDialog } from "@/components/ConfirmDialog";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/useAuth";
import { useT } from "@/lib/i18n/I18nProvider";
import { ICON_NAMES, resolveIcon } from "@/features/navigation/icons";
import {
  useCreateMenuItem,
  useDeleteMenuItem,
  useMenuItems,
  useReorderMenu,
  useUpdateMenuItem,
  type MenuItemInput,
  type MenuItemRow,
} from "@/features/localization/api";

const ALL_ROLES = ["admin", "staff"] as const;

export function MenusPage() {
  const t = useT();
  const { admin } = useAuth();

  if (admin?.role !== "admin") {
    return (
      <>
        <PageHeader title={t("menus.title", "Menu Management")} />
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            {t("menus.admin_only", "Only administrators can manage navigation.")}
          </CardContent>
        </Card>
      </>
    );
  }

  return <MenusManager />;
}

function MenusManager() {
  const t = useT();
  const query = useMenuItems();
  const reorder = useReorderMenu();
  const update = useUpdateMenuItem();
  const del = useDeleteMenuItem();
  const [addOpen, setAddOpen] = useState(false);
  const [editItem, setEditItem] = useState<MenuItemRow | null>(null);
  const [deleteItem, setDeleteItem] = useState<MenuItemRow | null>(null);

  const items = query.data ?? [];

  const move = (index: number, dir: -1 | 1) => {
    const next = [...items];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    reorder.mutate(next.map((i) => i.id));
  };

  return (
    <>
      <PageHeader
        title={t("menus.title", "Menu Management")}
        description={t(
          "menus.desc",
          "Create, reorder, show or hide navigation items and restrict them by role.",
        )}
        actions={
          <Button size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            {t("common.add", "Add")}
          </Button>
        }
      />

      <Card>
        <CardContent className="pt-6">
          {query.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[90px]">{t("menus.order", "Order")}</TableHead>
                  <TableHead>{t("menus.label", "Label")}</TableHead>
                  <TableHead>{t("menus.path", "Path")}</TableHead>
                  <TableHead>{t("menus.roles", "Roles")}</TableHead>
                  <TableHead>{t("menus.visible", "Visible")}</TableHead>
                  <TableHead className="text-right">{t("common.actions", "Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, i) => {
                  const Icon = resolveIcon(item.icon);
                  return (
                    <TableRow key={item.id} className={cn(!item.visible && "opacity-55")}>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            disabled={i === 0 || reorder.isPending}
                            onClick={() => move(i, -1)}
                          >
                            <ArrowUp className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            disabled={i === items.length - 1 || reorder.isPending}
                            onClick={() => move(i, 1)}
                          >
                            <ArrowDown className="size-4" />
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2 font-medium">
                          <Icon className="size-4 text-muted-foreground" />
                          {t(item.label_key, item.label_key)}
                        </div>
                        <span className="font-mono text-xs text-muted-foreground">
                          {item.label_key}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {item.path}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {item.roles.length === 0 ? (
                            <Badge variant="secondary">{t("menus.everyone", "everyone")}</Badge>
                          ) : (
                            item.roles.map((r) => (
                              <Badge key={r} variant={r === "admin" ? "default" : "muted"}>
                                {r}
                              </Badge>
                            ))
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1.5"
                          onClick={() =>
                            update.mutate({ id: item.id, visible: !item.visible })
                          }
                        >
                          {item.visible ? (
                            <>
                              <Eye className="size-4 text-emerald-600" />
                              {t("menus.visible", "Visible")}
                            </>
                          ) : (
                            <>
                              <EyeOff className="size-4 text-muted-foreground" />
                              {t("menus.hidden", "Hidden")}
                            </>
                          )}
                        </Button>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon" onClick={() => setEditItem(item)}>
                            <Pencil className="size-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeleteItem(item)}
                          >
                            <Trash2 className="size-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {addOpen && <MenuItemDialog onClose={() => setAddOpen(false)} />}
      {editItem && <MenuItemDialog item={editItem} onClose={() => setEditItem(null)} />}
      <ConfirmDialog
        open={deleteItem !== null}
        onOpenChange={(o) => !o && setDeleteItem(null)}
        title={t("menus.delete_title", "Delete menu item")}
        description={
          <>
            {t("menus.delete_prefix", "Remove")}{" "}
            <span className="font-mono">{deleteItem?.item_key}</span>{" "}
            {t("menus.delete_suffix", "from the navigation?")}
          </>
        }
        confirmLabel={t("common.delete", "Delete")}
        destructive
        onConfirm={() => del.mutateAsync(deleteItem!.id).then(() => setDeleteItem(null))}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Add / edit dialog
// --------------------------------------------------------------------------- //
function MenuItemDialog({ item, onClose }: { item?: MenuItemRow; onClose: () => void }) {
  const t = useT();
  const create = useCreateMenuItem();
  const update = useUpdateMenuItem();
  const isEdit = Boolean(item);

  const [itemKey, setItemKey] = useState(item?.item_key ?? "");
  const [labelKey, setLabelKey] = useState(item?.label_key ?? "");
  const [icon, setIcon] = useState(item?.icon ?? ICON_NAMES[0]);
  const [path, setPath] = useState(item?.path ?? "");
  const [roles, setRoles] = useState<string[]>(item?.roles ?? ["admin", "staff"]);
  const [error, setError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  useEffect(() => setError(null), [itemKey, labelKey, path]);

  const toggleRole = (role: string) =>
    setRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isEdit && !/^[a-z0-9_-]+$/.test(itemKey)) {
      setError(t("menus.key_invalid", "Item key: lowercase letters, numbers, dashes, underscores only."));
      return;
    }
    const body: MenuItemInput = { item_key: itemKey, label_key: labelKey, icon, path, roles };
    try {
      if (isEdit) {
        await update.mutateAsync({ id: item!.id, label_key: labelKey, icon, path, roles });
      } else {
        await create.mutateAsync(body);
      }
      onClose();
    } catch {
      /* toast handled globally */
    }
  };

  const PreviewIcon = resolveIcon(icon);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? t("menus.edit_title", "Edit menu item") : t("menus.add_title", "Add menu item")}</DialogTitle>
            <DialogDescription>
              {t("menus.dialog_desc", "The label is a translation key — edit its text under Settings → Localization.")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="mi-key">{t("menus.item_key", "Item key")}</Label>
                <Input
                  id="mi-key"
                  value={itemKey}
                  disabled={isEdit}
                  onChange={(e) => setItemKey(e.target.value)}
                  placeholder="reports"
                  className="font-mono"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mi-path">{t("menus.path", "Path")}</Label>
                <Input
                  id="mi-path"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="/reports"
                  className="font-mono"
                  required
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mi-label">{t("menus.label_key", "Label key")}</Label>
              <Input
                id="mi-label"
                value={labelKey}
                onChange={(e) => setLabelKey(e.target.value)}
                placeholder="nav.reports"
                className="font-mono"
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>{t("menus.icon", "Icon")}</Label>
                <div className="flex items-center gap-2">
                  <span className="flex size-9 items-center justify-center rounded-md border">
                    <PreviewIcon className="size-4" />
                  </span>
                  <Select value={icon ?? undefined} onValueChange={setIcon}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ICON_NAMES.map((name) => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>{t("menus.roles", "Roles")}</Label>
                <div className="flex gap-2 pt-1">
                  {ALL_ROLES.map((role) => (
                    <Button
                      key={role}
                      type="button"
                      variant={roles.includes(role) ? "default" : "outline"}
                      size="sm"
                      onClick={() => toggleRole(role)}
                    >
                      {role}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              {t("common.cancel", "Cancel")}
            </Button>
            <Button
              type="submit"
              disabled={pending || !itemKey.trim() || !labelKey.trim() || !path.trim()}
            >
              {pending && <Loader2 className="size-4 animate-spin" />}
              {isEdit ? t("common.save", "Save") : t("common.add", "Add")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
