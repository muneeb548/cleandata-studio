import type { ComponentType } from "react";
import { ToastProvider } from "@/components/ui/toast";
import { usePathname } from "@/lib/router";
import { AboutPage } from "@/pages/AboutPage";
import { ContactPage } from "@/pages/ContactPage";
import { LandingPage } from "@/pages/LandingPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
import { WorkspacePage } from "@/pages/WorkspacePage";

// Future blog articles can be added here, e.g. "/guides/how-to-clean-csv-files".
const ROUTES: Record<string, ComponentType> = {
  "/": LandingPage,
  "/app": WorkspacePage,
  "/about": AboutPage,
  "/privacy": PrivacyPage,
  "/contact": ContactPage,
};

export default function App() {
  const path = usePathname().replace(/\/+$/, "") || "/";
  const Page = ROUTES[path] ?? NotFoundPage;
  return (
    <ToastProvider>
      <Page />
    </ToastProvider>
  );
}
