import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  Mail,
  MessageCircle,
  MessageSquare,
  Plus,
  Send,
  Settings2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiClientError } from "@/types/api";
import { useT } from "@/lib/i18n/I18nProvider";
import {
  useOtpChannels,
  useOtpProviders,
  useTestOtpChannel,
  useUpdateOtpChannels,
  useUpdateOtpProvider,
  type OtpChannel,
  type OtpProvidersMasked,
  type ProviderUpdate,
} from "./api";

const ALL_CHANNELS: OtpChannel[] = ["whatsapp", "sms", "email"];

const CHANNEL_META: Record<
  OtpChannel,
  { icon: typeof Mail; labelKey: string; label: string }
> = {
  whatsapp: { icon: MessageCircle, labelKey: "settings.channel_whatsapp", label: "WhatsApp" },
  sms: { icon: MessageSquare, labelKey: "settings.channel_sms", label: "SMS" },
  email: { icon: Mail, labelKey: "settings.channel_email", label: "Email" },
};

type FieldType = "text" | "number" | "tls" | "secret";
interface ProviderField {
  name: string;
  label: string;
  type: FieldType;
  setFlag?: string;
  placeholder?: string;
}

const PROVIDER_FIELDS: Record<OtpChannel, ProviderField[]> = {
  whatsapp: [
    { name: "integrated_number", label: "Integrated / sender number", type: "text", placeholder: "+9715…" },
    { name: "template", label: "Template name", type: "text", placeholder: "izysafe_otp" },
    { name: "auth_key", label: "MSG91 auth key", type: "secret", setFlag: "auth_key_set" },
  ],
  sms: [
    { name: "account_sid", label: "Account SID", type: "text", placeholder: "AC…" },
    { name: "from_number", label: "From number", type: "text", placeholder: "+1…" },
    { name: "auth_token", label: "Auth token", type: "secret", setFlag: "auth_token_set" },
  ],
  email: [
    { name: "host", label: "SMTP host", type: "text", placeholder: "smtp.provider.com" },
    { name: "port", label: "Port", type: "number", placeholder: "587" },
    { name: "user", label: "Username", type: "text" },
    { name: "from_address", label: "From address", type: "text", placeholder: "no-reply@school.edu" },
    { name: "use_tls", label: "Use TLS", type: "tls" },
    { name: "password", label: "Password", type: "secret", setFlag: "password_set" },
  ],
};

/** Admin control for the app-wide OTP delivery channel order + per-channel provider
 *  credentials. Delivery tries each enabled channel in order (fallback priority).
 *  App-wide config (role=admin), mirroring localization. */
export function OtpChannelCard() {
  const t = useT();
  const query = useOtpChannels();
  const providers = useOtpProviders();
  const update = useUpdateOtpChannels();
  const [order, setOrder] = useState<OtpChannel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [configuring, setConfiguring] = useState<OtpChannel | null>(null);

  useEffect(() => {
    if (query.data) setOrder(query.data.channels);
  }, [query.data]);

  const available = ALL_CHANNELS.filter((c) => !order.includes(c));
  const dirty = query.data
    ? JSON.stringify(order) !== JSON.stringify(query.data.channels)
    : false;

  const touch = () => {
    setSaved(false);
    setError(null);
  };

  const move = (index: number, dir: -1 | 1) => {
    const next = [...order];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setOrder(next);
    touch();
  };

  const remove = (channel: OtpChannel) => {
    if (order.length <= 1) return; // at least one channel must stay enabled
    setOrder(order.filter((c) => c !== channel));
    touch();
  };

  const add = (channel: OtpChannel) => {
    setOrder([...order, channel]);
    touch();
  };

  const save = async () => {
    setError(null);
    setSaved(false);
    try {
      await update.mutateAsync(order);
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("settings.could_not_save", "Could not save."),
      );
    }
  };

  const isConfigured = (channel: OtpChannel): boolean => {
    const p = providers.data;
    if (!p) return false;
    if (channel === "whatsapp") return p.whatsapp.auth_key_set;
    if (channel === "sms") return p.sms.auth_token_set;
    return p.email.password_set;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.otp_channels", "OTP delivery channel")}</CardTitle>
        <CardDescription>
          {t(
            "settings.otp_channels_desc",
            "How parents receive their login code. Delivery tries each enabled channel in order and uses the first that succeeds. Use Configure to set each provider's credentials.",
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="text-sm font-medium text-destructive">
            {t("settings.otp_channels_load_error", "Failed to load OTP channels.")}
          </p>
        ) : (
          <div className="space-y-4">
            <ul className="space-y-2">
              {order.map((channel, index) => {
                const meta = CHANNEL_META[channel];
                const Icon = meta.icon;
                return (
                  <li
                    key={channel}
                    className="flex items-center gap-3 rounded-md border bg-card px-3 py-2"
                  >
                    <Badge variant="secondary" className="tabular-nums">
                      {index + 1}
                    </Badge>
                    <Icon className="size-4 text-muted-foreground" />
                    <span className="font-medium">{t(meta.labelKey, meta.label)}</span>
                    <Badge variant={isConfigured(channel) ? "success" : "muted"} className="py-0 text-[10px]">
                      {isConfigured(channel)
                        ? t("settings.configured", "Configured")
                        : t("settings.not_configured", "Not set")}
                    </Badge>
                    <div className="ml-auto flex items-center gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setConfiguring(channel)}
                      >
                        <Settings2 className="size-4" />
                        {t("settings.configure", "Configure")}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={t("settings.move_up", "Move up")}
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                      >
                        <ChevronUp className="size-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={t("settings.move_down", "Move down")}
                        disabled={index === order.length - 1}
                        onClick={() => move(index, 1)}
                      >
                        <ChevronDown className="size-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label={t("settings.disable_channel", "Disable channel")}
                        disabled={order.length <= 1}
                        onClick={() => remove(channel)}
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>

            {available.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {t("settings.add_channel", "Add channel")}:
                </span>
                {available.map((channel) => {
                  const meta = CHANNEL_META[channel];
                  const Icon = meta.icon;
                  return (
                    <Button
                      key={channel}
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => add(channel)}
                    >
                      <Plus className="size-4" />
                      <Icon className="size-4" />
                      {t(meta.labelKey, meta.label)}
                    </Button>
                  );
                })}
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              {t(
                "settings.otp_email_note",
                "Email is used only for parents who have an email address on file; otherwise delivery falls through to the next channel.",
              )}
            </p>

            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
            <div className="flex items-center gap-3">
              <Button type="button" disabled={!dirty || update.isPending} onClick={save}>
                {update.isPending && <Loader2 className="size-4 animate-spin" />}
                {t("settings.save_channels", "Save channels")}
              </Button>
              {saved && (
                <span className="text-sm font-medium text-emerald-600">
                  {t("settings.saved", "Saved ✓")}
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>

      {configuring && providers.data && (
        <ProviderDialog
          channel={configuring}
          masked={providers.data}
          onClose={() => setConfiguring(null)}
        />
      )}
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Per-channel credentials dialog + test send
// --------------------------------------------------------------------------- //
function ProviderDialog({
  channel,
  masked,
  onClose,
}: {
  channel: OtpChannel;
  masked: OtpProvidersMasked;
  onClose: () => void;
}) {
  const t = useT();
  const fields = PROVIDER_FIELDS[channel];
  const current = masked[channel] as Record<string, string | number | boolean>;
  const update = useUpdateOtpProvider(channel);
  const test = useTestOtpChannel(channel);
  const [error, setError] = useState<string | null>(null);
  const [recipient, setRecipient] = useState("");

  const [form, setForm] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of fields) {
      if (f.type === "secret") init[f.name] = "";
      else {
        const v = current[f.name];
        init[f.name] = v === undefined || v === null ? "" : String(v);
      }
    }
    return init;
  });

  const set = (name: string, value: string) =>
    setForm((prev) => ({ ...prev, [name]: value }));

  const save = async () => {
    setError(null);
    const payload: Record<string, string | number | boolean> = {};
    for (const f of fields) {
      const v = form[f.name] ?? "";
      if (f.type === "secret") {
        if (v.trim()) payload[f.name] = v.trim(); // blank = keep existing
      } else if (f.type === "number") {
        if (v.trim()) payload[f.name] = Number(v);
      } else if (f.type === "tls") {
        payload[f.name] = v === "true";
      } else {
        payload[f.name] = v;
      }
    }
    try {
      await update.mutateAsync(payload as ProviderUpdate);
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiClientError ? err.message : t("settings.could_not_save", "Could not save."),
      );
    }
  };

  const sendTest = async () => {
    setError(null);
    try {
      const res = await test.mutateAsync(recipient.trim());
      if (res.sent) toast.success(t("settings.test_sent", "Test message sent."));
      else toast.error(t("settings.test_failed", "Could not send — check the credentials."));
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : t("settings.test_failed", "Could not send — check the credentials."),
      );
    }
  };

  const meta = CHANNEL_META[channel];
  const recipientPlaceholder =
    channel === "email" ? "admin@example.com" : "+9715…";

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t("settings.configure_provider", "Configure")} {t(meta.labelKey, meta.label)}
          </DialogTitle>
          <DialogDescription>
            {t(
              "settings.configure_provider_desc",
              "These credentials override the server environment. Leave a secret blank to keep the stored value.",
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {fields.map((f) => {
            const id = `prov-${channel}-${f.name}`;
            if (f.type === "tls") {
              return (
                <div key={f.name} className="space-y-2">
                  <Label>{t(`settings.field_${f.name}`, f.label)}</Label>
                  <Select value={form[f.name]} onValueChange={(v) => set(f.name, v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">{t("common.yes", "Yes")}</SelectItem>
                      <SelectItem value="false">{t("common.no", "No")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              );
            }
            const isSecret = f.type === "secret";
            const secretSet = f.setFlag ? Boolean(current[f.setFlag]) : false;
            return (
              <div key={f.name} className="space-y-2">
                <Label htmlFor={id}>{t(`settings.field_${f.name}`, f.label)}</Label>
                <Input
                  id={id}
                  type={isSecret ? "password" : f.type === "number" ? "number" : "text"}
                  autoComplete={isSecret ? "new-password" : "off"}
                  value={form[f.name]}
                  onChange={(e) => set(f.name, e.target.value)}
                  placeholder={
                    isSecret
                      ? secretSet
                        ? t("settings.secret_set_ph", "•••• set — leave blank to keep")
                        : t("settings.secret_unset_ph", "Not set")
                      : f.placeholder ?? ""
                  }
                />
              </div>
            );
          })}
          {error && <p className="text-sm font-medium text-destructive">{error}</p>}
        </div>

        <div className="space-y-2 rounded-md border bg-muted/30 p-3">
          <Label htmlFor={`test-${channel}`}>
            {t("settings.send_test", "Send a test OTP")}
          </Label>
          <div className="flex gap-2">
            <Input
              id={`test-${channel}`}
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder={recipientPlaceholder}
            />
            <Button
              type="button"
              variant="outline"
              disabled={test.isPending || !recipient.trim()}
              onClick={sendTest}
            >
              {test.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
              {t("settings.send_test_btn", "Send test")}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t(
              "settings.send_test_note",
              "Uses the currently saved credentials for this channel.",
            )}
          </p>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={update.isPending}>
            {t("common.cancel", "Cancel")}
          </Button>
          <Button type="button" onClick={save} disabled={update.isPending}>
            {update.isPending && <Loader2 className="size-4 animate-spin" />}
            {t("common.save", "Save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
