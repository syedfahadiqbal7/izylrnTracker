import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  Mail,
  MessageCircle,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiClientError } from "@/types/api";
import { useT } from "@/lib/i18n/I18nProvider";
import { useOtpChannels, useUpdateOtpChannels, type OtpChannel } from "./api";

const ALL_CHANNELS: OtpChannel[] = ["whatsapp", "sms", "email"];

const CHANNEL_META: Record<
  OtpChannel,
  { icon: typeof Mail; labelKey: string; label: string }
> = {
  whatsapp: { icon: MessageCircle, labelKey: "settings.channel_whatsapp", label: "WhatsApp" },
  sms: { icon: MessageSquare, labelKey: "settings.channel_sms", label: "SMS" },
  email: { icon: Mail, labelKey: "settings.channel_email", label: "Email" },
};

/** Admin control for the app-wide OTP delivery channel order. Parents receive their
 *  login OTP on the first channel that delivers, falling back down the list — so the
 *  order is the fallback priority. App-wide config (role=admin), mirroring localization. */
export function OtpChannelCard() {
  const t = useT();
  const query = useOtpChannels();
  const update = useUpdateOtpChannels();
  const [order, setOrder] = useState<OtpChannel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

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

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.otp_channels", "OTP delivery channel")}</CardTitle>
        <CardDescription>
          {t(
            "settings.otp_channels_desc",
            "How parents receive their login code. Delivery tries each enabled channel in order and uses the first that succeeds.",
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
                    <span className="flex-1 font-medium">{t(meta.labelKey, meta.label)}</span>
                    <div className="flex items-center gap-1">
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
    </Card>
  );
}
