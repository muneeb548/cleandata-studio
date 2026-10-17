import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { usePageMeta } from "@/lib/seo";
import { useInitialHashScroll } from "@/lib/router";
import { StaticPage } from "./StaticPage";

export function PrivacyPage() {
  usePageMeta({
    title: "Privacy & Data Handling — CleanData Studio",
    description: "How CleanData Studio processes, stores and deletes the CSV files you upload.",
    path: "/privacy",
  });
  useInitialHashScroll();
  // Show the limits this server actually uses rather than hard-coded numbers.
  const [limits, setLimits] = useState<{ ttl: number; maxMb: number } | null>(null);
  useEffect(() => {
    api
      .config()
      .then((c) => setLimits({ ttl: c.session_ttl_minutes, maxMb: c.max_upload_mb }))
      .catch(() => setLimits(null));
  }, []);
  return (
    <StaticPage
      eyebrow="Privacy"
      title="Privacy and data handling"
      intro="This page describes exactly what happens to a file you upload to CleanData Studio version 1."
    >
      <section>
        <h2>What happens when you upload a file</h2>
        <ul>
          <li>Your CSV file is sent from your browser to the CleanData Studio server over the connection you use to open the site.</li>
          <li>While a file is imported, it is held in a private temporary file on the server, which is deleted as soon as the import finishes (or fails). The data is then kept only in the server's memory and is never stored in a database.</li>
          <li>When you download, the cleaned file is written to a temporary file, sent to you, and deleted immediately.</li>
          <li>Your data is not sent to external AI services or third-party APIs.</li>
          <li>Every upload gets a random, private session ID. Other users cannot access your session.</li>
        </ul>
        <p>
          Because the file is processed by a server, it does leave your device. If you run CleanData Studio on your own
          computer (as described in the project README), that server is your own computer.
        </p>
      </section>
      <section>
        <h2>How long data is kept</h2>
        <ul>
          <li>
            {limits
              ? `A session is deleted after ${limits.ttl} minutes without activity.`
              : "A session is deleted after a period of inactivity."}
          </li>
          <li>Starting over with a new file deletes the previous session.</li>
          <li>Restarting or updating the server deletes all sessions, so a session can also end earlier.</li>
          <li>When the server is busy, a session that has not been used for a while may be deleted to make room for new uploads.</li>
          <li>Your cleaned file is generated when you click Download; keep your own copy.</li>
        </ul>
      </section>
      <section>
        <h2>Logs</h2>
        <p>
          The application logs technical events such as errors and expired sessions. It does not log the contents of
          uploaded files, individual cell values, or search terms.
        </p>
        <p>
          When this site is hosted by a cloud provider, that provider operates the servers and network your data
          passes through (the encrypted HTTPS connection ends at the provider's network edge) and may keep its own
          connection logs, such as IP addresses and requested page addresses, under its own privacy policy.
        </p>
      </section>
      <section>
        <h2>What we do not do</h2>
        <ul>
          <li>No accounts, passwords or registration.</li>
          <li>No advertising or analytics trackers are included in this version.</li>
          <li>No selling or sharing of uploaded data.</li>
        </ul>
      </section>
      <section id="terms" tabIndex={-1} className="scroll-mt-20 outline-none">
        <h2>Terms of use</h2>
        <p>
          CleanData Studio is provided as is, without warranty. You are responsible for the data you upload and for
          checking cleaned results before relying on them. Do not upload data you are not permitted to process.
        </p>
      </section>
    </StaticPage>
  );
}
