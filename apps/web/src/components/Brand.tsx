export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-3 whitespace-nowrap" aria-label="OntoFoundry">
      <span className="grid rotate-45 grid-cols-[repeat(2,7px)] gap-0.5" aria-hidden="true">
        <i className="block h-[7px] bg-accent" />
        <i className="block h-[7px] bg-accent opacity-60" />
        <i className="block h-[7px] bg-accent opacity-60" />
        <i className="block h-[7px] bg-accent" />
      </span>
      {!compact && <span className="text-[15px] font-[650] text-ink">OntoFoundry</span>}
    </span>
  );
}
