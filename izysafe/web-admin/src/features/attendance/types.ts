/** Attendance reporting types — mirror the backend AttendanceReportResponse. */

export type AttendanceStatus =
  | "on_time"
  | "late"
  | "early"
  | "absent"
  | "unknown";

export interface AttendanceReportSummary {
  by_status: Record<AttendanceStatus, number>;
  records: number;
  students: number;
  /** (on_time + late + early) / records */
  present_rate: number;
}

export interface StudentAttendanceSummary {
  child_id: string;
  child_name: string;
  class_grade: string | null;
  on_time: number;
  late: number;
  early: number;
  absent: number;
  unknown: number;
  present_days: number;
  total_days: number;
  rate: number;
}

export interface AttendanceReport {
  date_from: string;
  date_to: string;
  class_grade: string | null;
  summary: AttendanceReportSummary;
  per_student: StudentAttendanceSummary[];
}

export interface ReportParams {
  from: string; // YYYY-MM-DD
  to: string; // YYYY-MM-DD
  class_grade?: string;
}
