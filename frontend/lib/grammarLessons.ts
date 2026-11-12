export interface GrammarLessonContent {
  skillId: string;
  title: string;
  summary: string;
  rules: {
    name: string;
    formula: string;
    usage: string;
  }[];
  examples: {
    sentence: string;
    explanation: string;
    type: "positive" | "negative" | "question";
  }[];
  mistakeAlerts: {
    wrong: string;
    correct: string;
    why: string;
  }[];
  quickTip: string;
}

export const GRAMMAR_LESSONS: Record<string, GrammarLessonContent> = {
  "grammar.present_simple_continuous": {
    skillId: "grammar.present_simple_continuous",
    title: "Present Simple vs. Present Continuous",
    summary:
      "Use Present Simple for regular habits, general truths, and permanent routines. Use Present Continuous for ongoing actions occurring right now or temporary situations.",
    rules: [
      {
        name: "Present Simple (Habits & Facts)",
        formula: "Subject + Base Verb (+ -s/-es for he/she/it)",
        usage: "Habits, schedules, universal scientific facts, and stative conditions.",
      },
      {
        name: "Present Continuous (In Progress)",
        formula: "Subject + am/is/are + Verb-ing",
        usage: "Actions taking place at the moment of speaking, or temporary current trends.",
      },
      {
        name: "Stative Verbs Exception",
        formula: "know, want, need, believe, like, understand (no -ing)",
        usage: "Stative verbs describe states rather than physical actions and rarely take continuous forms.",
      },
    ],
    examples: [
      {
        sentence: "Water boils at 100°C.",
        explanation: "Scientific fact — uses present simple.",
        type: "positive",
      },
      {
        sentence: "Listen! The baby is crying in the next room.",
        explanation: "'Listen!' signals an event currently unfolding right now.",
        type: "positive",
      },
      {
        sentence: "I know the answer (NOT: I am knowing).",
        explanation: "'Know' is a stative verb describing a mental state.",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "He don't like coffee.",
        correct: "He doesn't like coffee.",
        why: "With third-person singular (he/she/it), the auxiliary is 'does not' / 'doesn't'.",
      },
      {
        wrong: "I am knowing your brother.",
        correct: "I know your brother.",
        why: "'Know' expresses a relationship or state, so it never takes the -ing form.",
      },
    ],
    quickTip:
      "Look for trigger adverbs: 'always', 'usually', 'every day' signal Present Simple. 'Now', 'right now', 'at the moment', 'Look!', 'Listen!' signal Present Continuous.",
  },
  "grammar.past_simple_present_perfect": {
    skillId: "grammar.past_simple_present_perfect",
    title: "Past Simple vs. Present Perfect",
    summary:
      "Use Past Simple for completed actions tied to a finished time in the past. Use Present Perfect for life experiences, unfinished periods, or past actions that connect directly to the present.",
    rules: [
      {
        name: "Past Simple (Finished Time)",
        formula: "Subject + Past Verb (-ed or irregular)",
        usage: "Completed past actions where the exact time is specified (yesterday, last year, in 2010).",
      },
      {
        name: "Present Perfect (Experience & Present Result)",
        formula: "Subject + have/has + Past Participle (V3)",
        usage: "Life experiences, actions continuing from past to present (since/for), or recent news with current relevance.",
      },
    ],
    examples: [
      {
        sentence: "We visited Paris last summer.",
        explanation: "'Last summer' is a closed, finished past time.",
        type: "positive",
      },
      {
        sentence: "I have visited Paris three times in my life.",
        explanation: "Life experience with an open time frame extending into the present.",
        type: "positive",
      },
      {
        sentence: "She has lived here since 2018.",
        explanation: "Action started in the past and still continues right now.",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "I have seen that film yesterday.",
        correct: "I saw that film yesterday.",
        why: "'Yesterday' is a finished time frame; present perfect cannot be used with specific finished times.",
      },
      {
        wrong: "He has finished homework two hours ago.",
        correct: "He finished homework two hours ago.",
        why: "'Ago' always requires the past simple tense.",
      },
    ],
    quickTip:
      "Use 'for' with a duration of time (for 5 years) and 'since' with a specific starting point (since Monday, since 2020).",
  },
  "grammar.articles": {
    skillId: "grammar.articles",
    title: "Articles: A, An, The & Zero Article",
    summary:
      "Determiners identify whether a noun is specific or general. 'A/An' introduces singular countable general nouns; 'The' refers to specific known nouns; zero article is used for generalizations and uncountables.",
    rules: [
      {
        name: "Indefinite: A / An",
        formula: "A + consonant sound / An + vowel sound",
        usage: "Singular countable nouns mentioned for the first time or non-specific members of a group.",
      },
      {
        name: "Definite: The",
        formula: "The + singular/plural/uncountable noun",
        usage: "Nouns already known to both speaker and listener, unique things (the sun), or superlatives.",
      },
      {
        name: "Zero Article (Ø)",
        formula: "No article + plural or uncountable noun",
        usage: "Talking about things in general, abstract ideas (honesty), or single mountain peaks / lakes.",
      },
    ],
    examples: [
      {
        sentence: "She is a university student.",
        explanation: "'University' begins with a /j/ consonant sound, so use 'a', not 'an'.",
        type: "positive",
      },
      {
        sentence: "Could you close the door, please?",
        explanation: "Both speakers know which door is being referred to in the room.",
        type: "positive",
      },
      {
        sentence: "Honesty is vital in friendships.",
        explanation: "Abstract noun used in a broad, general sense takes no article.",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "My sister is a engineer.",
        correct: "My sister is an engineer.",
        why: "'Engineer' starts with a vowel sound /e/, requiring 'an'.",
      },
      {
        wrong: "The Mount Everest is high.",
        correct: "Mount Everest is high.",
        why: "Individual mountains take no article (unlike mountain ranges like 'the Alps').",
      },
    ],
    quickTip:
      "Choose 'a' vs 'an' by the sound that follows, not the letter spelling! (e.g., an hour, a European city).",
  },
  "grammar.prepositions_time_place": {
    skillId: "grammar.prepositions_time_place",
    title: "Prepositions of Time and Place (At, On, In)",
    summary:
      "Master the pyramid of prepositions: 'In' for broad/enclosed contexts, 'On' for surfaces/days, and 'At' for exact points/times.",
    rules: [
      {
        name: "At (Precise & Points)",
        formula: "At + exact clock time, specific address, or point",
        usage: "at 9:00, at noon, at night, at the station, at the door.",
      },
      {
        name: "On (Surfaces & Specific Days)",
        formula: "On + calendar day, date, surface, or public transit",
        usage: "on Monday, on May 5th, on the table, on the bus.",
      },
      {
        name: "In (Enclosed & Broad Timeframes)",
        formula: "In + month, year, season, century, city, country",
        usage: "in May, in 2024, in summer, in Hanoi, in the room.",
      },
    ],
    examples: [
      {
        sentence: "The train departs at 7:30 AM.",
        explanation: "Exact clock time takes 'at'.",
        type: "positive",
      },
      {
        sentence: "We always celebrate on New Year's Day.",
        explanation: "Specific calendar days take 'on'.",
        type: "positive",
      },
      {
        sentence: "Leaves turn orange in autumn.",
        explanation: "Seasons of the year take 'in'.",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "My birthday is on May.",
        correct: "My birthday is in May.",
        why: "Months without a specific day take 'in'. (If a day is included: 'on May 12th').",
      },
    ],
    quickTip:
      "Think of a triangle: IN is the wide base (centuries, countries), ON is the middle (days, streets), AT is the sharp point (hours, exact spots).",
  },
  "grammar.comparatives_superlatives": {
    skillId: "grammar.comparatives_superlatives",
    title: "Comparatives & Superlatives",
    summary:
      "Compare two things using comparatives (-er / more ... than) or identify the extreme among three or more using superlatives (the -est / the most).",
    rules: [
      {
        name: "Short Adjectives (1 syllable)",
        formula: "Adjective + -er than / The + adjective + -est",
        usage: "fast → faster than → the fastest; big → bigger than → the biggest.",
      },
      {
        name: "Long Adjectives (2+ syllables)",
        formula: "More + adjective + than / The most + adjective",
        usage: "expensive → more expensive than → the most expensive.",
      },
      {
        name: "Irregular Forms",
        formula: "good → better → best; bad → worse → worst; far → further → furthest",
        usage: "These change completely and don't add -er or -est.",
      },
    ],
    examples: [
      {
        sentence: "This laptop is more powerful than my old one.",
        explanation: "Three-syllable adjective 'powerful' uses 'more ... than'.",
        type: "positive",
      },
      {
        sentence: "Jupiter is the largest planet in our solar system.",
        explanation: "Superlative comparison among all planets takes 'the largest'.",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "She is more taller than me.",
        correct: "She is taller than me.",
        why: "Never combine 'more' with an '-er' suffix (double comparative).",
      },
      {
        wrong: "He is the most good player.",
        correct: "He is the best player.",
        why: "'Good' has an irregular superlative form: 'best'.",
      },
    ],
    quickTip:
      "Two-syllable adjectives ending in '-y' behave like short adjectives: change 'y' to 'i' and add '-er' / '-est' (happy → happier → happiest).",
  },
  "grammar.conditionals": {
    skillId: "grammar.conditionals",
    title: "Conditionals (Zero, First, Second, Third)",
    summary:
      "Describe cause and effect across factual truths (Zero), realistic future outcomes (First), hypothetical present situations (Second), and past regrets (Third).",
    rules: [
      {
        name: "Zero Conditional (Universal Truth)",
        formula: "If + Present Simple, Present Simple",
        usage: "If you heat ice, it melts.",
      },
      {
        name: "First Conditional (Real Future Possibility)",
        formula: "If + Present Simple, will + Base Verb",
        usage: "If it rains tomorrow, we will cancel the picnic.",
      },
      {
        name: "Second Conditional (Hypothetical Present)",
        formula: "If + Past Simple, would + Base Verb",
        usage: "If I won the lottery, I would travel the globe.",
      },
      {
        name: "Third Conditional (Unreal Past / Regret)",
        formula: "If + Past Perfect, would have + Past Participle",
        usage: "If she had studied harder, she would have passed.",
      },
    ],
    examples: [
      {
        sentence: "If you press this button, the machine starts.",
        explanation: "Zero conditional for an immediate operational rule.",
        type: "positive",
      },
      {
        sentence: "If I have enough time tonight, I will call you.",
        explanation: "First conditional for a real future probability.",
        type: "positive",
      },
      {
        sentence: "If I were you, I would take the offer.",
        explanation: "Second conditional advice ('were' is preferred for all subjects).",
        type: "positive",
      },
    ],
    mistakeAlerts: [
      {
        wrong: "If it will rain tomorrow, I will stay home.",
        correct: "If it rains tomorrow, I will stay home.",
        why: "Do not use 'will' in the 'if'-clause in the first conditional.",
      },
    ],
    quickTip:
      "Remember the golden rule: never put 'will' or 'would' inside the 'if' condition clause!",
  },
};
