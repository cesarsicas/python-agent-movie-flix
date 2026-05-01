import httpx
from langchain_core.tools import tool
from config import settings


async def _spring_get(path: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(
        base_url=settings.spring_base_url,
        timeout=settings.request_timeout,
    ) as client:
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()


def _fmt_search_results(results: list) -> str:
    if not results:
        return "No titles found."
    lines = []
    for r in results[:10]:
        year = f" ({r['year']})" if r.get("year") else ""
        kind = r.get("type", "")
        link = f"{settings.frontend_base_url}/title/details/{r['id']}"
        lines.append(f"- [{r['name']}{year}]({link}) [{kind}] (id: {r['id']})")
    return "\n".join(lines)


def _fmt_releases(results: list) -> str:
    if not results:
        return "No recent releases found."
    lines = []
    for r in results[:10]:
        date = r.get("source_release_date", "")
        source = r.get("source_name", "")
        kind = r.get("type", "")
        date_str = f" — {date}" if date else ""
        source_str = f" on {source}" if source else ""
        link = f"{settings.frontend_base_url}/title/details/{r['external_id']}"
        lines.append(f"- [{r['title']}]({link}) [{kind}]{source_str}{date_str} (id: {r['external_id']})")
    return "\n".join(lines)


def _fmt_details(d: dict, external_id: int) -> str:
    title = d.get("title", "Unknown")
    year = d.get("year") or ""
    kind = d.get("type", "")
    plot = d.get("plot_overview") or "No synopsis available."
    runtime = d.get("runtime_minutes")
    rating = d.get("user_rating")
    critic = d.get("critic_score")
    genres = d.get("genre_names") or []
    us_rating = d.get("us_rating") or ""

    link = f"{settings.frontend_base_url}/title/details/{external_id}"
    poster = d.get("poster")

    parts = []
    if poster:
        parts.append(f"[![poster]({poster})]({link})")
    parts.append(f"[{title} ({year})]({link}) [{kind}]")
    if genres:
        parts.append(f"Genres: {', '.join(genres)}")
    meta = []
    if runtime:
        meta.append(f"{runtime} min")
    if us_rating:
        meta.append(us_rating)
    if rating:
        meta.append(f"Rating: {rating:.1f}/10")
    if critic:
        meta.append(f"Critic score: {critic}")
    if meta:
        parts.append(" | ".join(meta))
    parts.append(plot)
    parts.append(f"Watch here: {link}")
    return "\n".join(parts)


def _fmt_reviews(results: list) -> str:
    if not results:
        return "No user reviews yet."
    lines = []
    for r in results[:5]:
        name = r.get("defaultUserName", "Anonymous")
        text = r.get("review", "")
        lines.append(f'"{text}" — {name}')
    return "\n".join(lines)


@tool
async def search_titles(query: str) -> str:
    """Search for movies and TV shows by title, genre, mood, theme, or description.
    Use this when the user asks for recommendations or wants to find specific content.
    Returns a list of matching titles with their id (use this id to get details or reviews)."""
    try:
        data = await _spring_get("/titles/search", params={"query": query})
        return _fmt_search_results(data)
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."
    except httpx.HTTPStatusError as e:
        return f"Search unavailable (HTTP {e.response.status_code}). Please try again."


@tool
async def get_title_details(external_id: int) -> str:
    """Get full details about a specific movie or TV show: synopsis, runtime, rating, genres.
    Use the id returned by search_titles or get_releases as the external_id."""
    try:
        data = await _spring_get(f"/titles/{external_id}")
        return _fmt_details(data, external_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Title with id {external_id} not found."
        return f"Could not fetch title details (HTTP {e.response.status_code})."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."


@tool
async def get_title_reviews(external_id: int) -> str:
    """Get user reviews for a specific movie or TV show.
    Use the id returned by search_titles as the external_id."""
    try:
        data = await _spring_get(f"/titles/{external_id}/reviews")
        return _fmt_reviews(data)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No reviews found for title id {external_id}."
        return f"Could not fetch reviews (HTTP {e.response.status_code})."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."


@tool
async def get_releases() -> str:
    """Get the latest movie and TV show releases available on the platform.
    Use this when the user asks what's new, trending, or recently added.
    Returns titles with their id (use this id to get details)."""
    try:
        data = await _spring_get("/titles/releases")
        return _fmt_releases(data)
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."
    except httpx.HTTPStatusError as e:
        return f"Could not fetch releases (HTTP {e.response.status_code})."


@tool
async def get_current_transmission() -> str:
    """Get what movie is currently being streamed live on the platform right now.
    Use this when the user asks what's playing live or on air."""
    try:
        data = await _spring_get("/transmissions/current")
        name = data.get("movieName", "Unknown")
        start = data.get("startTime", "")
        duration = data.get("duration")
        duration_str = f", running {duration} minutes" if duration else ""
        return f"Currently live: {name} (started at {start}{duration_str})"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return "No live transmission is active right now."
        return f"Could not fetch live transmission info (HTTP {e.response.status_code})."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Could not reach the platform. Please try again in a moment."
