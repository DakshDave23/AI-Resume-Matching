import type { Candidate } from "@/api/candidates";
import { degreeName } from "@/lib/candidate";

const FIELD_RESULT = {
  not_required: "The JD names no field of study.",
  match: "Field of study matches.",
  different: "A different field of study, which lowers the education score.",
  unknown: "No field of study found on the resume, so no penalty.",
};

/** What the JD asks for, what the resume has, and how education was scored. */
export function EducationPanel({ candidate }: { candidate: Candidate }) {
  const education = candidate.explanation.details.education;
  const required =
    education.required_level === null ? "No degree stated" : degreeName(education.required_level);
  return (
    <div className="space-y-6">
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border p-3">
          <dt className="text-sm text-muted-foreground">The JD asks for</dt>
          <dd className="mt-1 font-medium">{required}</dd>
          {education.required_fields.length > 0 && (
            <dd className="text-sm text-muted-foreground">
              in {education.required_fields.join(", ")}
            </dd>
          )}
        </div>
        <div className="rounded-lg border p-3">
          <dt className="text-sm text-muted-foreground">Highest on the resume</dt>
          <dd className="mt-1 font-medium">{degreeName(education.candidate_level)}</dd>
          {education.candidate_field && (
            <dd className="text-sm text-muted-foreground">in {education.candidate_field}</dd>
          )}
        </div>
      </dl>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {education.level_score === null ? (
          <li>The JD names no degree, so education isn't scored.</li>
        ) : (
          <li>Degree level score: {education.level_score.toFixed(2)} of 1</li>
        )}
        <li>
          {FIELD_RESULT[education.field_result]}
          {education.matched_field && education.field_result === "match"
            ? ` (${education.matched_field})`
            : ""}
        </li>
        {education.waived_by_experience && (
          <li>
            The JD accepts equivalent experience, and enough relevant years made up for the degree.
          </li>
        )}
      </ul>
      <section aria-label="Education entries" className="space-y-2">
        <h3 className="font-medium">Education on the resume</h3>
        {candidate.educations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No education entries were found.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {candidate.educations.map((e, i) => (
              <li key={i} className="p-3 text-sm">
                <p className="font-medium">
                  {e.degree ?? degreeName(e.degree_level)}
                  {e.field_of_study && ` in ${e.field_of_study}`}
                </p>
                <p className="text-muted-foreground">
                  {[e.institution, e.graduation_year].filter(Boolean).join(" · ") || "—"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
