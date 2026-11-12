import type { Metadata } from "next";

// The page is a client component, so its tab title ("AI Monkey · Banana English") lives here.
export const metadata: Metadata = { title: "AI Monkey" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
