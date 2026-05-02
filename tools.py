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


def _fmt_autocomplete(data: dict) -> str:
    results = data.get("results", [])
    if not results:
        return "No titles or people found."
    lines = []
    for r in results[:10]:
        name = r.get("name", "")
        year = f" ({r['year']})" if r.get("year") else ""
        result_type = r.get("result_type") or r.get("type", "")
        rid = r.get("id")
        if result_type in ("movie", "tv_movie", "tv_series", "tv_miniseries", "tv_special", "tv_short"):
            link = f"{settings.frontend_base_url}/title/details/{rid}"
            lines.append(f"- [{name}{year}]({link}) [{result_type}] (id: {rid})")
        else:
            lines.append(f"- {name} [person] (external_id: {rid})")
    return "\n".join(lines)


def _fmt_list_titles(data: dict) -> str:
    titles = data.get("titles", [])
    if not titles:
        return "No titles found matching those criteria."
    total = data.get("total_results", 0)
    page = data.get("page", 1)
    lines = [f"Found {total} titles (page {page}):"]
    for r in titles:
        year = f" ({r['year']})" if r.get("year") else ""
        kind = r.get("type", "")
        ext_id = r.get("externalId") or r.get("id")
        link = f"{settings.frontend_base_url}/title/details/{ext_id}"
        lines.append(f"- [{r['title']}{year}]({link}) [{kind}] (id: {ext_id})")
    return "\n".join(lines)


def _fmt_person(d: dict) -> str:
    name = d.get("full_name") or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
    ext_id = d.get("externalId") or d.get("id")
    professions = [p for p in [d.get("main_profession"), d.get("secondary_profession"), d.get("tertiary_profession")] if p]
    parts = [f"**{name}** (external_id: {ext_id})"]
    if professions:
        parts.append(f"Profession: {', '.join(professions)}")
    if d.get("date_of_birth"):
        place = d.get("place_of_birth")
        birth_str = f"Born: {d['date_of_birth']}"
        if place:
            birth_str += f" in {place}"
        if d.get("date_of_death"):
            birth_str += f" — Died: {d['date_of_death']}"
        parts.append(birth_str)
    if d.get("headshot_url"):
        parts.append(f"![{name}]({d['headshot_url']})")
    return "\n".join(parts)


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
async def search_titles(query: str, filter_type: str = "TITLES_AND_PEOPLE") -> str:
    """Primary search tool — always use this first when looking up any movie, TV show, or person by name.
    Returns titles (with id for get_title_details) and people (with person_id for get_person or list_titles).

    filter_type controls what kinds of results to return:
      TITLES_AND_PEOPLE — default, returns both titles and people
      TITLES_ONLY       — any title (movies + TV shows)
      MOVIES_ONLY       — movies only
      TV_SHOWS_ONLY     — TV shows only
      PEOPLE_ONLY       — actors, directors, and other people
    """
    params = {"query": query, "filterResultType": filter_type}
    try:
        data = await _spring_get("/titles/autocomplete-search", params=params)
        return _fmt_autocomplete(data)
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


@tool
async def list_titles(
    genres: str | None = None,
    types: str | None = None,
    sort_by: str = "relevance_desc",
    release_date_start: int | None = None,
    release_date_end: int | None = None,
    user_rating_low: float | None = None,
    user_rating_high: float | None = None,
    critic_score_low: int | None = None,
    critic_score_high: int | None = None,
    person_id: int | None = None,
    limit: int = 10,
) -> str:
    """Browse and filter movies and TV shows by genre, content type, year range, ratings, or by a specific person.
    Use this for discovery queries like 'recommend horror movies', 'top rated comedies', 'sci-fi from the 90s', or 'films starring [actor]'.
    When filtering by genre, call get_genres first to obtain the correct genre externalId values.
    person_id must be obtained first from search_titles or get_person.

    genres: comma-separated genre externalIds from get_genres (e.g. "15" or "6,21")
    types: comma-separated content types — movie, tv_movie, tv_series, tv_miniseries, tv_special
    sort_by: relevance_desc, relevance_asc, release_date_desc, release_date_asc, rating_desc, rating_asc
    release_date_start / release_date_end: 4-digit year, e.g. 1990 or 2024
    user_rating_low / user_rating_high: 0.0–10.0 scale
    critic_score_low / critic_score_high: 0–100 scale
    person_id: filter titles featuring a specific actor or director (use the external_id from search_titles)
    limit: number of results (max 10)
    """
    params: dict = {"sort_by": sort_by, "limit": min(limit, 10)}
    if genres:
        params["genres"] = genres
    if types:
        params["types"] = types
    if release_date_start is not None:
        params["release_date_start"] = release_date_start
    if release_date_end is not None:
        params["release_date_end"] = release_date_end
    if user_rating_low is not None:
        params["user_rating_low"] = user_rating_low
    if user_rating_high is not None:
        params["user_rating_high"] = user_rating_high
    if critic_score_low is not None:
        params["critic_score_low"] = critic_score_low
    if critic_score_high is not None:
        params["critic_score_high"] = critic_score_high
    if person_id is not None:
        params["person_id"] = person_id
    try:
        data = await _spring_get("/titles/list", params=params)
        return _fmt_list_titles(data)
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."
    except httpx.HTTPStatusError as e:
        return f"Could not fetch titles (HTTP {e.response.status_code}). Please try again."


@tool
async def get_genres() -> str:
    """Get the full list of available genres with their IDs.
    Call this before using list_titles with a genre filter so you have the correct genre externalId.
    Returns each genre's name and externalId (use externalId as the genres param in list_titles)."""
    try:
        data = await _spring_get("/titles/genres")
        if not data:
            return "No genres available."
        lines = [f"- {g['name']} (id: {g['externalId']})" for g in data]
        return "\n".join(lines)
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."
    except httpx.HTTPStatusError as e:
        return f"Could not fetch genres (HTTP {e.response.status_code})."


@tool
async def get_person(external_id: int) -> str:
    """Get biography and career details for an actor, director, or other film/TV person.
    Use the external_id returned by search_titles for a person result.
    Returns name, professions, date of birth, and place of birth."""
    try:
        data = await _spring_get(f"/titles/person/{external_id}")
        return _fmt_person(data)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Person with external_id {external_id} not found."
        return f"Could not fetch person details (HTTP {e.response.status_code})."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."
