import { request, type Schemas } from "@/api/client";

export type Job = Schemas["JobOut"];
export type JobSkill = Schemas["JobSkillOut"];
export type RequirementsUpdate = Schemas["RequirementsUpdate"];
export type SkillChipIn = Schemas["SkillRequirementIn"];
export type Skill = Schemas["SkillOut"];

const JSON_HEADERS = { "Content-Type": "application/json" };

export function createJob(body: { title?: string; text: string }): Promise<Job> {
  return request<Job>("/jobs", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function uploadJob(file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  return request<Job>("/jobs/upload", { method: "POST", body: form });
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function updateRequirements(jobId: string, body: RequirementsUpdate): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}/requirements`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function searchSkills(query: string, limit = 8): Promise<Skill[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request<Skill[]>(`/skills?${params}`);
}

export type JobSummary = Schemas["JobSummaryOut"];
export type JobList = Schemas["JobListOut"];

/** Newest first, with each job's resume count and best match. */
export function listJobs(limit = 50): Promise<JobList> {
  return request<JobList>(`/jobs?limit=${limit}`);
}

/** The demo: the sample Backend Java job plus the 15 sample resumes, parsing in the background. */
export function loadSampleData(): Promise<Schemas["BatchCreatedOut"]> {
  return request<Schemas["BatchCreatedOut"]>("/sample-data", { method: "POST" });
}
