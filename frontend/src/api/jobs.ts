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
