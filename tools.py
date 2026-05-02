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
            person_link = f"{settings.frontend_base_url}/person/{rid}"
            lines.append(f"- [{name}]({person_link}) [person] (id: {rid})")
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



@tool
async def search_titles_and_people(query: str, filter_type: str = "TITLES_AND_PEOPLE") -> str:
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
async def get_title_cast(external_id: int) -> str:
    """Get the cast and directors of a movie or TV show as clickable links to their profile pages.
    Use this when the user asks who acts in a title or wants to see the cast.
    Use the id returned by search_titles as the external_id.
    IMPORTANT: output this list exactly as returned — every name is already a clickable markdown link."""
    try:
        data = await _spring_get(f"/titles/{external_id}")
        cast = data.get("cast") or []
        if not cast:
            return "No cast information available for this title."
        actors = sorted(
            [m for m in cast if m.get("type") == "Actor"],
            key=lambda m: m.get("order", 999),
        )
        directors = [m for m in cast if m.get("type") == "Director"]
        parts = []
        if actors:
            parts.append("**Cast:**")
            for m in actors:
                person_link = f"{settings.frontend_base_url}/person/{m['person_id']}"
                role = f" as {m['role']}" if m.get("role") else ""
                parts.append(f"- [{m['full_name']}]({person_link}){role}")
        if directors:
            parts.append("**Director(s):**")
            for m in directors:
                person_link = f"{settings.frontend_base_url}/person/{m['person_id']}"
                parts.append(f"- [{m['full_name']}]({person_link})")
        return "\n".join(parts)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Title with id {external_id} not found."
        return f"Could not fetch cast (HTTP {e.response.status_code})."
    except (httpx.ConnectError, httpx.TimeoutException):
        return "Movie database is temporarily unreachable. Please try again in a moment."



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
async def get_person_details(external_id: int) -> str:
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
