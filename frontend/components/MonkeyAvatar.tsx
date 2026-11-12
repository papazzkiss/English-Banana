/** AI Monkey: an anime-style monkey drawn in SVG. `state` drives the animations (see
 * .monkey-avatar in globals.css); `mini` is the static icon used in the navigation bar. */

export type MonkeyState = "idle" | "listening" | "hearing" | "thinking" | "talking";

const FUR = "#8a5a3b";
const FUR_DARK = "#6e4429";
const FACE = "#f6d9bb";
const EAR = "#f1bf9a";
const INK = "#2b1a12";

export function MonkeyAvatar({ state = "idle", size = 160, mini = false }: {
  state?: MonkeyState; size?: number; mini?: boolean;
}) {
  return (
    <svg
      className={`monkey-avatar ${mini ? "mini" : `is-${state}`}`}
      width={size} height={size} viewBox="0 0 200 200" aria-hidden
    >
      {!mini && <circle className="ring" cx="100" cy="104" r="94" />}
      <g className="head">
        {/* ears */}
        <circle cx="36" cy="104" r="26" fill={FUR} />
        <circle cx="36" cy="104" r="15" fill={EAR} />
        <circle cx="164" cy="104" r="26" fill={FUR} />
        <circle cx="164" cy="104" r="15" fill={EAR} />
        {/* head + hair tuft */}
        <circle cx="100" cy="102" r="64" fill={FUR} />
        <path d="M88 44 C86 28 100 22 108 30 C100 30 98 36 102 42 Z" fill={FUR_DARK} />
        {/* banana hair clip */}
        <path d="M122 44 C138 40 152 48 156 62 C146 54 134 52 124 54 Z" fill="#f2c230"
          stroke="#b98d00" strokeWidth="2" strokeLinejoin="round" />
        {/* face */}
        <ellipse cx="78" cy="100" rx="27" ry="29" fill={FACE} />
        <ellipse cx="122" cy="100" rx="27" ry="29" fill={FACE} />
        <ellipse cx="100" cy="130" rx="42" ry="28" fill={FACE} />
        {/* eyes: big and glossy */}
        <g className="eyes">
          <ellipse cx="80" cy="102" rx="12.5" ry="16" fill={INK} />
          <ellipse cx="120" cy="102" rx="12.5" ry="16" fill={INK} />
          <ellipse cx="80" cy="108" rx="8" ry="7" fill="#6b4330" />
          <ellipse cx="120" cy="108" rx="8" ry="7" fill="#6b4330" />
          <circle cx="84.5" cy="95" r="5" fill="#fff" />
          <circle cx="124.5" cy="95" r="5" fill="#fff" />
          <circle cx="76" cy="109" r="2.2" fill="#fff" />
          <circle cx="116" cy="109" r="2.2" fill="#fff" />
        </g>
        {/* blush */}
        <ellipse cx="63" cy="124" rx="9" ry="5" fill="#ff8fa3" opacity="0.55" />
        <ellipse cx="137" cy="124" rx="9" ry="5" fill="#ff8fa3" opacity="0.55" />
        {/* nose */}
        <circle cx="95" cy="123" r="2.2" fill={FUR_DARK} />
        <circle cx="105" cy="123" r="2.2" fill={FUR_DARK} />
        {/* mouth: a smile, or an animated open mouth while talking */}
        {state === "talking" && !mini ? (
          <g className="mouth-talk">
            <ellipse cx="100" cy="140" rx="10" ry="7" fill="#7a2e2e" />
            <ellipse cx="100" cy="144" rx="6" ry="3" fill="#ff8f8f" />
          </g>
        ) : state === "thinking" && !mini ? (
          <path d="M94 141 Q100 138 106 141" stroke={INK} strokeWidth="3" fill="none"
            strokeLinecap="round" />
        ) : (
          <path d="M88 136 Q100 148 112 136" stroke={INK} strokeWidth="3.2" fill="none"
            strokeLinecap="round" />
        )}
      </g>
      {state === "thinking" && !mini && (
        <g className="dots" fill="var(--text-muted)">
          <circle cx="150" cy="40" r="5" />
          <circle cx="166" cy="30" r="6" />
          <circle cx="184" cy="18" r="7" />
        </g>
      )}
    </svg>
  );
}
