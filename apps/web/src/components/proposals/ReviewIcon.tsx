/** Match the approved prototype's icon geometry, rather than substituting glyphs. */
export function ReviewIcon({ name }: { name: "search" | "evidence" | "chevron" }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24">
    {name === "search" ? <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></> :
      <path d={name === "evidence" ? "M14 3H5v18h14V8l-5-5Z M14 3v5h5 M8 12h8 M8 16h6" : "m6 9 6 6 6-6"} />}
  </svg>;
}
