import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { CandidatePage } from "@/pages/CandidatePage";
import { JobPage } from "@/pages/JobPage";
import { JobsPage } from "@/pages/JobsPage";
import { NewJobPage } from "@/pages/NewJobPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RankingsPage } from "@/pages/RankingsPage";
import { UploadPage } from "@/pages/UploadPage";

/** Jobs home, then the three-step wizard (Job → Resumes → Results), then a candidate. */
export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <JobsPage /> },
      { path: "/jobs/new", element: <NewJobPage /> },
      { path: "/jobs/:jobId", element: <JobPage /> },
      { path: "/jobs/:jobId/upload", element: <UploadPage /> },
      { path: "/jobs/:jobId/rankings", element: <RankingsPage /> },
      { path: "/jobs/:jobId/candidates/:resumeId", element: <CandidatePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
