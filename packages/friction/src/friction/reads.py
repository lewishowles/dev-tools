"""Read grouped friction summaries from SQLite."""

from collections.abc import Sequence

from .database import Database

# Categories that stay hidden unless a caller explicitly includes them.
AUTOMATED_CATEGORIES = frozenset({"check-fail", "tool-error"})


def summary(
	database: Database,
	categories: Sequence[str] = (),
	include_check_fails: bool = False,
	include_tool_errors: bool = False,
) -> list[dict[str, object]]:
	"""Return active events grouped by category, directory, and exact detail."""
	conditions = [
		"""
		NOT EXISTS (
			SELECT 1
			FROM resolutions
			WHERE resolutions.category = events.category
				AND resolutions.pattern = events.detail
				AND resolutions.resolved_at_utc >= events.timestamp_utc
		)
		"""
	]
	parameters: list[str] = []
	if categories:
		placeholders = ", ".join("?" for _ in categories)
		conditions.append(f"events.category IN ({placeholders})")
		parameters.extend(categories)

	excluded_categories = set(AUTOMATED_CATEGORIES)
	if include_check_fails:
		excluded_categories.discard("check-fail")
	if include_tool_errors:
		excluded_categories.discard("tool-error")
	if excluded_categories:
		placeholders = ", ".join("?" for _ in excluded_categories)
		conditions.append(f"events.category NOT IN ({placeholders})")
		parameters.extend(sorted(excluded_categories))

	where_clause = " AND ".join(conditions)
	with database.connection() as connection:
		rows = connection.execute(
			f"""
			SELECT
				COUNT(*) AS count,
				category,
				cwd,
				detail
			FROM events
			WHERE {where_clause}
			GROUP BY category, cwd, detail
			ORDER BY count DESC, category, cwd, detail
			""",
			parameters,
		).fetchall()

	return [dict(row) for row in rows]
