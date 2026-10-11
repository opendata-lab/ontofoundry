// Renders nothing without tags: an empty tag row is noise, not information.
export function TagList({ tags }: { tags: readonly string[] }) {
  if (!tags.length) return null;
  return (
    <span className="tag-list">
      {tags.map((tag, index) => (
        <span className="tag tag--label" key={`${tag}:${index}`}>
          {tag}
        </span>
      ))}
    </span>
  );
}
