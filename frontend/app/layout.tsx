import type { Metadata, Viewport } from "next";
import { Outfit, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { LearnerProvider } from "@/components/LearnerProvider";
import { MonkeyProvider } from "@/components/MonkeyProvider";

// Self-hosted at build time: no request to Google from the learner's browser, no layout shift.
const display = Outfit({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-display" });
const body = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-body" });

export const metadata: Metadata = {
  title: {
    default: "Banana English",
    template: "%s · Banana English",
  },
  description:
    "Adaptive English practice: vocabulary, grammar, listening, speaking and conversation, " +
    "with feedback on every answer and a plan built from what you get wrong.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍌</text></svg>",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f7f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0e1015" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <LearnerProvider>
          <MonkeyProvider>
            <AppShell>{children}</AppShell>
          </MonkeyProvider>
        </LearnerProvider>
      </body>
    </html>
  );
}
