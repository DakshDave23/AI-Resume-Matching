import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section>
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted-foreground">
        <Link to="/" className="underline">
          Back to jobs
        </Link>
      </p>
    </section>
  );
}
