import { useState } from "react";
import { X } from "lucide-react";

const splitTags = (value: string) => value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean);
const uniqueTags = (tags: string[]) => [...new Set(tags)];

export function TagEditor({ tags, onChange }: { tags: string[]; onChange: (tags: string[]) => void }) {
  const [committed, setCommitted] = useState(() => uniqueTags(tags));
  const [text, setText] = useState("");
  const commit = (value = text) => {
    const next = uniqueTags([...committed, ...splitTags(value)]);
    setCommitted(next);
    setText("");
    if (next.length !== tags.length || next.some((tag, index) => tag !== tags[index])) onChange(next);
  };
  const remove = (tag: string) => {
    const next = committed.filter((value) => value !== tag);
    setCommitted(next);
    onChange(uniqueTags([...next, ...splitTags(text)]));
  };
  return (
    <div className="tag-editor">
      {committed.map((tag) => (
        <span className="tag tag--label" key={tag}>
          {tag}
          <button type="button" aria-label={`移除标签 ${tag}`} onClick={() => remove(tag)}>
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        aria-label="标签"
        placeholder="添加标签"
        value={text}
        onChange={(e) => {
          const value = e.target.value;
          if (/[,，]/.test(value)) commit(value);
          else {
            setText(value);
            // Keep unfinished input in the draft so Save and navigation guards see it.
            onChange(uniqueTags([...committed, ...splitTags(value)]));
          }
        }}
        onBlur={() => commit()}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !text && committed.length) {
            e.preventDefault();
            remove(committed[committed.length - 1]);
          }
        }}
      />
    </div>
  );
}
