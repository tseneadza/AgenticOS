/**
 * PathDisplay Component
 *
 * Renders an API path with parameter segments highlighted.
 * Parameters are marked with curly braces: {param}
 * All colors use theme variables for full theme compatibility.
 *
 * Example:
 *   <PathDisplay path="/users/{userId}/posts/{postId}" />
 *   Renders: /users/ [highlighted: {userId}] /posts/ [highlighted: {postId}]
 *
 * @param {string} path - The API path to display (e.g., "/api/users/{id}")
 */

const styles = `
.path-segment-param {
  color: var(--accent);
  font-weight: 500;
}
`;

export default function PathDisplay({ path }) {
  if (!path) return null;

  // Split path by parameter placeholders: {param}
  // The /(...) capture group keeps the delimiters in the result
  const segments = path.split(/(\{[^}]+\})/);

  return (
    <>
      <style>{styles}</style>
      {segments.map((seg, i) => {
        // Parameters are wrapped in curly braces
        const isParam = seg.startsWith("{") && seg.endsWith("}");

        return (
          <span
            key={i}
            data-testid={`path-segment-${i}`}
            className={isParam ? "path-segment-param" : ""}
          >
            {seg}
          </span>
        );
      })}
    </>
  );
}
