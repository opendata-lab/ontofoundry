/**
 * Lines of `a` and `b` outside their longest common subsequence: what a line
 * diff marks as removed and added. Element JSON is small; a pathological size
 * falls back to comparing line by line.
 */
export function lineDiff(a: string[], b: string[]): { removed: boolean[]; added: boolean[] } {
  const removed = a.map(() => false);
  const added = b.map(() => false);
  if (a.length * b.length > 1_000_000) {
    a.forEach((line, i) => (removed[i] = line !== b[i]));
    b.forEach((line, j) => (added[j] = line !== a[j]));
    return { removed, added };
  }
  const width = b.length + 1;
  const lcs = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      lcs[i * width + j] =
        a[i] === b[j]
          ? lcs[(i + 1) * width + j + 1] + 1
          : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1]);
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      i++;
      j++;
    } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) removed[i++] = true;
    else added[j++] = true;
  }
  while (i < a.length) removed[i++] = true;
  while (j < b.length) added[j++] = true;
  return { removed, added };
}
