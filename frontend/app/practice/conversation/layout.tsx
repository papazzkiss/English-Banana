import type { Metadata } from "next";

// The page is a client component, so its tab title ("Conversation · Banana English") lives here.
export const metadata: Metadata = { title: "Conversation" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
