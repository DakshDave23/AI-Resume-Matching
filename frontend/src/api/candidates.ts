import { API_BASE_URL, request, type Schemas } from "@/api/client";

export type Candidate = Schemas["CandidateOut"];
export type MatchedSkill = Schemas["MatchedSkillOut"];
export type MissingSkill = Schemas["MissingSkillOut"];
export type RequirementMatch = Schemas["RequirementMatchOut"];
export type Breakdown = Schemas["BreakdownOut"];
export type EvidenceItem = Schemas["EvidenceItemOut"];
export type Role = Schemas["RoleOut"];
export type Explanation = Schemas["ExplanationOut"];

export function getCandidate(jobId: string, resumeId: string): Promise<Candidate> {
  return request<Candidate>(
    `/jobs/${encodeURIComponent(jobId)}/candidates/${encodeURIComponent(resumeId)}`,
  );
}

/** The uploaded file itself: PDFs open in the browser, DOCX files download. */
export function resumeFileUrl(resumeId: string): string {
  return `${API_BASE_URL}/resumes/${encodeURIComponent(resumeId)}/file`;
}
