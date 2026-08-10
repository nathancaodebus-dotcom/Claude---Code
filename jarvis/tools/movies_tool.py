"""Upcoming movie release dates via TMDb's free API."""
from __future__ import annotations

import httpx

from core.config import config
from tools.base import Tool


class UpcomingMoviesTool(Tool):
    name = "get_upcoming_movies"
    description = "Get upcoming movie theatrical release dates."
    input_schema = {
        "type": "object",
        "properties": {"max_results": {"type": "integer", "description": "Default 10."}},
    }

    def run(self, max_results: int = 10) -> str:
        response = httpx.get(
            "https://api.themoviedb.org/3/movie/upcoming",
            params={"api_key": config.tmdb_api_key},
            timeout=10,
        )
        response.raise_for_status()
        movies = response.json().get("results", [])[:max_results]
        if not movies:
            return "No upcoming movies found."
        return "\n".join(f"- {m['title']} — {m.get('release_date', '?')}" for m in movies)


class SearchMovieTool(Tool):
    name = "search_movie"
    description = "Search for a movie and get its release date, overview, and rating."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, query: str) -> str:
        response = httpx.get(
            "https://api.themoviedb.org/3/search/movie",
            params={"api_key": config.tmdb_api_key, "query": query},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return f"No movie found matching '{query}'."
        movie = results[0]
        return (
            f"{movie['title']} ({movie.get('release_date', '?')}) — rating {movie.get('vote_average', '?')}/10\n"
            f"{movie.get('overview', '')}"
        )
