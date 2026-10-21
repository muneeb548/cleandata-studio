import { ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Link } from "@/lib/router";
import { usePageMeta } from "@/lib/seo";
import { StaticPage } from "./StaticPage";

export function AboutPage() {
  usePageMeta({
    title: "About CleanData Studio",
    description: "Why CleanData Studio exists, who it is for, and how it is built.",
    path: "/about",
  });
  return (
    <StaticPage
      eyebrow="About"
      title="Clean data without writing code"
      intro="CleanData Studio is a focused workspace for preparing tabular data. It helps students, analysts, researchers and small businesses fix common data quality problems before analysis."
    >
      <section>
        <h2>Why it exists</h2>
        <p>
          Most analysis problems start with the data: duplicated records, empty cells, inconsistent spelling, numbers
          stored as text. Fixing these in a spreadsheet is slow and easy to get wrong; fixing them in code requires
          programming knowledge. CleanData Studio offers a middle ground — real data cleaning operations with a clear,
          reviewable workflow.
        </p>
      </section>
      <section>
        <h2>Principles</h2>
        <ul>
          <li>Nothing changes until you preview and apply it.</li>
          <li>The original upload is kept separately and can always be restored.</li>
          <li>Every number shown is calculated from your actual data.</li>
          <li>Features are only listed when they are implemented.</li>
        </ul>
      </section>
      <section>
        <h2>How it is built</h2>
        <p>
          The interface is built with React and TypeScript. All data processing happens in a Python backend using
          FastAPI and pandas. It reads CSV, TSV, Excel and JSON files and exports CSV or Excel. An optional AI assistant turns plain-language
          requests and questions into the app's own validated steps; the AI never runs code and never receives the full file.
        </p>
      </section>
      <Link href="/app" className={buttonVariants()}>
        Open the workspace <ArrowRight />
      </Link>
    </StaticPage>
  );
}
