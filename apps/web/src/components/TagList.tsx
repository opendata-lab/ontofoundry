export function TagList({
  tags,
  empty = "未设置",
}: {
  tags: readonly string[];
  empty?: string;
}) {
  return (
    <span className="tag-list">
      {tags.length ? (
        tags.map((tag, index) => (
          <span className="tag tag--label" key={`${tag}:${index}`}>
            {tag}
          </span>
        ))
      ) : (
        <span className="muted">{empty}</span>
      )}
    </span>
  );
}
