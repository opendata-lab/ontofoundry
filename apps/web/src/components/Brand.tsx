export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-3 whitespace-nowrap" aria-label="OntoFoundry">
      <span className="brand-mark" aria-hidden="true">
        <i className="brand-tile" />
        <i className="brand-tile brand-tile-muted" />
        <i className="brand-tile brand-tile-muted" />
        <i className="brand-tile" />
      </span>
      {!compact && <span className="text-base font-semibold text-ink">OntoFoundry</span>}
    </span>
  );
}
