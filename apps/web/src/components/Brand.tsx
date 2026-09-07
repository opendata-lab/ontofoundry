export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="brand" aria-label="OntoFoundry">
      <span className="brand__mark" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
      {!compact && <span className="brand__name">OntoFoundry</span>}
    </span>
  );
}
