/** Settings data hooks: school config update + admin/staff management. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";
import type { School } from "@/features/school/api";

export type AdminRole = "admin" | "staff";

export interface SchoolAdminRow {
  id: string;
  school_id: string;
  email: string;
  name: string | null;
  role: AdminRole;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface SchoolUpdate {
  name?: string;
  address?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  timezone?: string;
  holidays?: string[];
  on_time_before?: string;
  late_until?: string;
  arrival_window_from?: string;
  day_ends_at?: string;
}

export function useUpdateSchool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SchoolUpdate) => apiPut<School>("/schools/me", input),
    onSuccess: () => {
      toast.success("Settings saved");
      qc.invalidateQueries({ queryKey: ["school-me"] });
    },
  });
}

// -------------------------------------------------------------- my account
export function useUpdateMyName() {
  return useMutation({
    mutationFn: (name: string) => apiPatch("/schools/admins/me", { name }),
    onSuccess: () => toast.success("Profile updated"),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiPost("/schools/admins/me/password", body),
    onSuccess: () => toast.success("Password updated"),
  });
}

// ------------------------------------------------------- admins & staff
export function useAdmins() {
  return useQuery({
    queryKey: ["admins"],
    queryFn: () => apiGet<SchoolAdminRow[]>("/schools/admins"),
  });
}

export function useInviteStaff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      email: string;
      password: string;
      name?: string;
      role: AdminRole;
    }) => apiPost<SchoolAdminRow>("/schools/admins", body),
    onSuccess: (a) => {
      toast.success(`${a.email} added`);
      qc.invalidateQueries({ queryKey: ["admins"] });
    },
  });
}

export function useManageAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      role?: AdminRole;
      name?: string;
    }) => apiPatch<SchoolAdminRow>(`/schools/admins/${id}`, body),
    onSuccess: () => {
      toast.success("Member updated");
      qc.invalidateQueries({ queryKey: ["admins"] });
    },
  });
}

export function useSetAdminActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiPost<SchoolAdminRow>(
        `/schools/admins/${id}/${active ? "reactivate" : "deactivate"}`,
      ),
    onSuccess: (_a, v) => {
      toast.success(v.active ? "Member reactivated" : "Member deactivated");
      qc.invalidateQueries({ queryKey: ["admins"] });
    },
  });
}

export function useDeleteAdmin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/schools/admins/${id}`),
    onSuccess: () => {
      toast.success("Member removed");
      qc.invalidateQueries({ queryKey: ["admins"] });
    },
  });
}

// --------------------------------------------------- OTP delivery channel (app-wide)
export type OtpChannel = "whatsapp" | "sms" | "email";

export interface OtpChannels {
  channels: OtpChannel[];
}

export function useOtpChannels() {
  return useQuery({
    queryKey: ["otp-channels"],
    queryFn: () => apiGet<OtpChannels>("/schools/otp-channels"),
  });
}

export function useUpdateOtpChannels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (channels: OtpChannel[]) =>
      apiPut<OtpChannels>("/schools/otp-channels", { channels }),
    onSuccess: () => {
      toast.success("OTP channels saved");
      qc.invalidateQueries({ queryKey: ["otp-channels"] });
    },
  });
}

// ---------------------------------------------- OTP provider credentials (masked)
export interface OtpProvidersMasked {
  whatsapp: { auth_key_set: boolean; template: string; integrated_number: string };
  sms: { auth_token_set: boolean; account_sid: string; from_number: string };
  email: {
    password_set: boolean;
    host: string;
    port: number;
    user: string;
    from_address: string;
    use_tls: boolean;
  };
}

export type WhatsAppProviderUpdate = Partial<{
  auth_key: string;
  template: string;
  integrated_number: string;
}>;
export type SmsProviderUpdate = Partial<{
  account_sid: string;
  auth_token: string;
  from_number: string;
}>;
export type EmailProviderUpdate = Partial<{
  host: string;
  port: number;
  user: string;
  password: string;
  from_address: string;
  use_tls: boolean;
}>;

export function useOtpProviders() {
  return useQuery({
    queryKey: ["otp-providers"],
    queryFn: () => apiGet<OtpProvidersMasked>("/schools/otp-providers"),
  });
}

export type ProviderUpdate = WhatsAppProviderUpdate &
  SmsProviderUpdate &
  EmailProviderUpdate;

export function useUpdateOtpProvider(channel: OtpChannel) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderUpdate) =>
      apiPut<OtpProvidersMasked>(`/schools/otp-providers/${channel}`, body),
    onSuccess: () => {
      toast.success("Credentials saved");
      qc.invalidateQueries({ queryKey: ["otp-providers"] });
    },
  });
}

export function useTestOtpChannel(channel: OtpChannel) {
  return useMutation({
    mutationFn: (recipient: string) =>
      apiPost<{ sent: boolean }>(`/schools/otp-providers/${channel}/test`, { recipient }),
  });
}
