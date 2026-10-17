import { useState, type FormEvent } from "react";
import { ExternalLink, Mail } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FieldHint, Label, Select } from "@/components/ui/form";
import { CONTACT_EMAIL, GITHUB_URL } from "@/content/site";
import { usePageMeta } from "@/lib/seo";
import { StaticPage } from "./StaticPage";

/**
 * Version 1 has no email backend, so the form opens the visitor's own email
 * app with the message pre-filled. If no contact address is configured, the
 * form says so instead of pretending to send anything.
 */
export function ContactPage() {
  usePageMeta({
    title: "Contact & Feedback — CleanData Studio",
    description: "Report a problem, suggest a feature or ask a question about CleanData Studio.",
    path: "/contact",
  });
  const [topic, setTopic] = useState("Feedback");
  const [message, setMessage] = useState("");
  const [opened, setOpened] = useState(false);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!CONTACT_EMAIL || !message.trim()) return;
    const subject = encodeURIComponent(`CleanData Studio: ${topic}`);
    const body = encodeURIComponent(message.trim());
    window.location.href = `mailto:${CONTACT_EMAIL}?subject=${subject}&body=${body}`;
    setOpened(true);
  };

  return (
    <StaticPage
      eyebrow="Contact"
      title="Contact and feedback"
      intro="Found a bug, have an idea, or a CSV that doesn't import correctly? Let us know. Please don't include private data in your message."
    >
      {!CONTACT_EMAIL && (
        <Alert tone="warning" title="Contact email is not configured">
          The site owner has not set a contact address yet (VITE_CONTACT_EMAIL). The form below is disabled until it is.
        </Alert>
      )}
      <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-border p-5" aria-label="Feedback form">
        <div className="space-y-1.5">
          <Label htmlFor="topic">Topic</Label>
          <Select id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} disabled={!CONTACT_EMAIL}>
            <option>Feedback</option>
            <option>Bug report</option>
            <option>Feature request</option>
            <option>Question</option>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="message">Message</Label>
          <textarea
            id="message"
            rows={6}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={!CONTACT_EMAIL}
            maxLength={4000}
            required
            className="w-full rounded-md border border-border-strong px-3 py-2 text-body focus-visible:border-primary disabled:bg-muted"
            placeholder="Describe what happened or what you'd like to see…"
          />
          <FieldHint>Submitting opens your email app with this message filled in. Nothing is sent from this website.</FieldHint>
        </div>
        <Button type="submit" disabled={!CONTACT_EMAIL || !message.trim()}>
          <Mail /> Open in email app
        </Button>
        {opened && <p className="text-body text-muted-foreground" role="status">Your email app should have opened. If not, write to {CONTACT_EMAIL}.</p>}
      </form>
      {GITHUB_URL && (
        <p>
          You can also open an issue on{" "}
          <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
            GitHub <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
          .
        </p>
      )}
    </StaticPage>
  );
}
