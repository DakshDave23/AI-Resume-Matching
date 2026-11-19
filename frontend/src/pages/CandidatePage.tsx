import { ArrowLeft, ChevronLeft, ChevronRight, Link2, Mail, MapPin, Phone } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { resumeFileUrl } from "@/api/candidates";
import { ApiError } from "@/api/client";
import { EducationPanel } from "@/components/candidate/EducationPanel";
import { ExperienceComparison } from "@/components/candidate/ExperienceComparison";
import { ExplanationList } from "@/components/candidate/ExplanationList";
import { RequirementMatchTable } from "@/components/candidate/RequirementMatchTable";
import { ResumeTextViewer } from "@/components/candidate/ResumeTextViewer";
import { ScoreBreakdown } from "@/components/candidate/ScoreBreakdown";
import { ScoreGauge } from "@/components/candidate/ScoreGauge";
import { SkillsPanel } from "@/components/candidate/SkillsPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCandidate } from "@/hooks/useCandidate";
import { useJob } from "@/hooks/useJobs";
import { useRankings } from "@/hooks/useRankings";
import { neighbours } from "@/lib/candidate";
import { displayName } from "@/lib/rankings";

/** Why a candidate got their score: gauge, breakdown and one tab per part of the analysis. */
export function CandidatePage() {
  const { jobId = "", resumeId = "" } = useParams();
  const { data: job } = useJob(jobId);
  const { data: candidate, error, isPending } = useCandidate(jobId, resumeId);
  const { data: ranking } = useRankings(jobId);
  const around = neighbours(ranking?.rows ?? [], resumeId);
  const rankingsPath = `/jobs/${jobId}/rankings`;

  const terms = useMemo(
    () =>
      (candidate?.matched_skills ?? []).flatMap((m) =>
        m.matched_skill ? [m.skill, m.matched_skill] : [m.skill],
      ),
    [candidate],
  );

  const step = (to: { resume_id: string } | null, label: string, icon: "prev" | "next") => {
    const content =
      icon === "prev" ? (
        <>
          <ChevronLeft aria-hidden /> {label}
        </>
      ) : (
        <>
          {label} <ChevronRight aria-hidden />
        </>
      );
    return to ? (
      <Button variant="outline" size="sm" asChild>
        <Link to={`/jobs/${jobId}/candidates/${to.resume_id}`}>{content}</Link>
      </Button>
    ) : (
      <Button variant="outline" size="sm" disabled>
        {content}
      </Button>
    );
  };
  const nav = (
    <nav aria-label="Candidates" className="flex items-center gap-2">
      {step(around.previous, "Previous", "prev")}
      {around.position !== null && (
        <span className="text-sm text-muted-foreground tabular-nums">
          {around.position} of {around.total}
        </span>
      )}
      {step(around.next, "Next", "next")}
    </nav>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to={rankingsPath}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden /> Rankings
          {job && <span>· {job.title}</span>}
        </Link>
        {nav}
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error instanceof ApiError ? error.message : "This candidate couldn't be loaded."}
        </p>
      ) : isPending ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" aria-label="Loading candidate" />
      ) : (
        <>
          <header className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold">{displayName(candidate)}</h1>
              {candidate.rank !== null && <Badge variant="secondary">Rank {candidate.rank}</Badge>}
              {candidate.parse_confidence !== null &&
                (candidate.needs_review ? (
                  <Badge variant="outline" className="border-amber-400 text-amber-700">
                    Parse confidence {Math.round(candidate.parse_confidence * 100)}%: check by hand
                  </Badge>
                ) : (
                  <Badge variant="outline">
                    Parse confidence {Math.round(candidate.parse_confidence * 100)}%
                  </Badge>
                ))}
            </div>
            <p className="text-muted-foreground">{candidate.current_title ?? "No current title"}</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {candidate.email && (
                <li className="inline-flex items-center gap-1">
                  <Mail className="size-4 text-muted-foreground" aria-hidden />
                  <a href={`mailto:${candidate.email}`} className="hover:underline">
                    {candidate.email}
                  </a>
                </li>
              )}
              {candidate.phone && (
                <li className="inline-flex items-center gap-1">
                  <Phone className="size-4 text-muted-foreground" aria-hidden />
                  {candidate.phone}
                </li>
              )}
              {candidate.location && (
                <li className="inline-flex items-center gap-1">
                  <MapPin className="size-4 text-muted-foreground" aria-hidden />
                  {candidate.location}
                </li>
              )}
              {candidate.linkedin_url && (
                <li className="inline-flex items-center gap-1">
                  <Link2 className="size-4 text-muted-foreground" aria-hidden />
                  <a
                    href={candidate.linkedin_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline"
                  >
                    LinkedIn
                  </a>
                </li>
              )}
              {candidate.github_url && (
                <li className="inline-flex items-center gap-1">
                  <Link2 className="size-4 text-muted-foreground" aria-hidden />
                  <a
                    href={candidate.github_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline"
                  >
                    GitHub
                  </a>
                </li>
              )}
            </ul>
          </header>

          {candidate.is_stale && (
            <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
              The requirements changed after this score was worked out. Re-score from the{" "}
              <Link to={rankingsPath} className="font-medium underline">
                rankings
              </Link>
              .
            </p>
          )}

          <section
            aria-label="Score"
            className="flex flex-col gap-6 rounded-lg border p-5 sm:flex-row sm:items-center"
          >
            <div className="flex flex-col items-center gap-2 sm:w-56">
              <ScoreGauge score={candidate.match_percent} verdict={candidate.explanation.verdict} />
              <p className="text-center text-sm text-muted-foreground">
                {candidate.explanation.summary}
              </p>
            </div>
            <ScoreBreakdown
              parts={candidate.explanation.breakdown}
              total={candidate.explanation.score}
            />
          </section>

          <Tabs defaultValue="overview">
            <TabsList className="h-auto flex-wrap">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="skills">Skills</TabsTrigger>
              <TabsTrigger value="experience">Experience</TabsTrigger>
              <TabsTrigger value="requirements">Requirements</TabsTrigger>
              <TabsTrigger value="education">Education</TabsTrigger>
              <TabsTrigger value="resume">Resume</TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="grid gap-6 pt-4 md:grid-cols-2">
              <ExplanationList
                title="Top strengths"
                kind="strength"
                items={candidate.explanation.strengths}
                empty="No points earned."
              />
              <ExplanationList
                title="Top gaps"
                kind="gap"
                items={candidate.explanation.gaps}
                empty="No points lost."
              />
              {candidate.explanation.notes.length > 0 && (
                <section aria-label="Notes" className="space-y-2 md:col-span-2">
                  <h3 className="font-medium">Notes</h3>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {candidate.explanation.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                </section>
              )}
            </TabsContent>
            <TabsContent value="skills" className="pt-4">
              <SkillsPanel matched={candidate.matched_skills} missing={candidate.missing_skills} />
            </TabsContent>
            <TabsContent value="experience" className="pt-4">
              <ExperienceComparison candidate={candidate} />
            </TabsContent>
            <TabsContent value="requirements" className="pt-4">
              <RequirementMatchTable matches={candidate.requirement_matches} />
            </TabsContent>
            <TabsContent value="education" className="pt-4">
              <EducationPanel candidate={candidate} />
            </TabsContent>
            <TabsContent value="resume" className="pt-4">
              <ResumeTextViewer
                text={candidate.raw_text}
                terms={terms}
                fileUrl={resumeFileUrl(candidate.resume_id)}
                filename={candidate.filename}
              />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
