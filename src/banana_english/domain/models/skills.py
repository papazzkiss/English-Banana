"""Skill tags that are not derived from content files (vocabulary / grammar tags are)."""

LISTENING_SKILL = "listening.comprehension"
SPEAKING_GRAMMAR_SKILL = "speaking.grammar"
SPEAKING_FLUENCY_SKILL = "speaking.fluency"
CONVERSATION_SKILL = "conversation.communication"

# Skills scored from an answer that is already stored as another attempt: one spoken answer is
# saved twice (speaking.grammar + speaking.fluency) so each skill keeps its own score and
# mastery. Answer counts, activity, streaks and the recent list skip these rows, so one answer
# is counted once.
COMPANION_SKILLS = frozenset({SPEAKING_FLUENCY_SKILL})
