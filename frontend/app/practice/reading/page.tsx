"use client";

import { useLearner } from "@/components/useLearner";
import { BankPractice } from "@/components/bank/BankPractice";
import { PageHeader } from "@/components/ui/PageHeader";

/** Reading: texts from everyday notices to Wikipedia articles, each with its own questions. */
export default function ReadingPractice() {
  const { profile } = useLearner();
  if (!profile) return null;
  return (
    <>
      <PageHeader
        back={{ href: "/practice", label: "Practice" }}
        title="Reading"
        description="Read a short text, then answer questions about the main idea, the details and the words. Every set is new, and answers are checked instantly."
      />
      <BankPractice skill="reading" defaultLevel={profile.current_level} />
    </>
  );
}
