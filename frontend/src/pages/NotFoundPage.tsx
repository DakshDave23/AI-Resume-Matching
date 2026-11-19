import { SearchX } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common/States";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <EmptyState
      icon={SearchX}
      title="Page not found"
      action={
        <Button asChild>
          <Link to="/">Back to jobs</Link>
        </Button>
      }
    >
      There's nothing at this address.
    </EmptyState>
  );
}
