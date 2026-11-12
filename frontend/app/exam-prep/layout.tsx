import type { Metadata } from "next";

// The page is a client component, so its tab title ("Exam Prep · Banana English") lives here.
export const metadata: Metadata = { title: "Exam Prep" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
