import { api } from "./api";

export interface CourseRead {
  id: number;
  slug: string;
  title: string;
  description: string;
  duration_weeks: number;
  target_level: "beginner" | "intermediate" | "advanced";
  status: "draft" | "active" | "archived";
}

export interface EnrollmentRead {
  id: number;
  user_id: number;
  course_id: number;
  current_week: number;
  current_day_in_week: number;
  status: "active" | "paused" | "completed" | "abandoned";
  started_at: string | null;
  course: CourseRead;
}

export const coursesApi = {
  list: () => api.get<CourseRead[]>("/courses").then((r) => r.data),

  enroll: (payload: { course_slug: string }) =>
    api.post<EnrollmentRead>("/courses/enroll", payload).then((r) => r.data),
};
