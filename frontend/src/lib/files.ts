/**
 * Checks before upload (design doc §9: "checks before upload"). They mirror the API's own
 * rules, so most bad files are caught here with a clear reason; the API still checks
 * the real file type from its first bytes.
 */
export const MAX_FILE_MB = 5;
export const MAX_FILES = 50;
export const RESUME_TYPES = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
};
const EXTENSIONS = [".pdf", ".docx"];

export interface Rejection {
  name: string;
  reason: string;
}

const sameFile = (a: File, b: File) => a.name === b.name && a.size === b.size;

/** Which dropped files can join `chosen`, and why the others can't. */
export function checkFiles(
  dropped: File[],
  chosen: File[],
): { accepted: File[]; rejected: Rejection[] } {
  const accepted: File[] = [];
  const rejected: Rejection[] = [];
  for (const file of dropped) {
    const lower = file.name.toLowerCase();
    let reason: string | null = null;
    if (!EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      reason = "Only PDF and DOCX files can be uploaded.";
    } else if (file.size === 0) {
      reason = "The file is empty.";
    } else if (file.size > MAX_FILE_MB * 1024 * 1024) {
      reason = `The file is larger than ${MAX_FILE_MB} MB.`;
    } else if ([...chosen, ...accepted].some((other) => sameFile(other, file))) {
      reason = "This file is already in the list.";
    } else if (chosen.length + accepted.length >= MAX_FILES) {
      reason = `At most ${MAX_FILES} files can be uploaded at once.`;
    }
    if (reason) rejected.push({ name: file.name, reason });
    else accepted.push(file);
  }
  return { accepted, rejected };
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
