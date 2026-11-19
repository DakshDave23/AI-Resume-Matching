import { lazy } from "react";

// The wizard pages load on first visit (AppLayout shows a skeleton meanwhile), so the home
// page doesn't wait for the table, dropzone and candidate code.
export const NewJobPage = lazy(() =>
  import("@/pages/NewJobPage").then((m) => ({ default: m.NewJobPage })),
);
export const JobPage = lazy(() => import("@/pages/JobPage").then((m) => ({ default: m.JobPage })));
export const UploadPage = lazy(() =>
  import("@/pages/UploadPage").then((m) => ({ default: m.UploadPage })),
);
export const RankingsPage = lazy(() =>
  import("@/pages/RankingsPage").then((m) => ({ default: m.RankingsPage })),
);
export const CandidatePage = lazy(() =>
  import("@/pages/CandidatePage").then((m) => ({ default: m.CandidatePage })),
);
