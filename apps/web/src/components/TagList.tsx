import { Tag } from "antd";

// Renders nothing without tags: an empty tag row is noise, not information.
export function TagList({ tags }: { tags: readonly string[] }) {
  if (!tags.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {tags.map((tag, index) => (
        <Tag key={`${tag}:${index}`} className="!m-0">
          {tag}
        </Tag>
      ))}
    </span>
  );
}
