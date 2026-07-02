export function MasteredBadge({ pattern }: { pattern?: string }) {
  return (
    <span className="inline-flex items-center font-sans text-[9px] font-semibold uppercase tracking-wide text-verdant bg-verdant/[0.12] rounded-[10px] px-2 py-0.5">
      {pattern ? `✓ ${pattern} mastered` : "✓ Mastered"}
    </span>
  );
}

export default MasteredBadge;
