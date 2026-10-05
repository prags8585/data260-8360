#!/usr/bin/env python3


import logging
import sys
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s meals %(levelname)s %(message)s", force=True)
log = logging.getLogger("meals")

API_BASE = "https://www.themealdb.com/api/json/v1/1"
NO_MATCHES = {"results": [], "message": "no matches"}

mcp = FastMCP("meals")


def _get(path: str, **params: Any) -> list[dict] | None:
    """GET one TheMealDB endpoint and return its "meals" list (None when there are no results)."""
    url = f"{API_BASE}/{path}"
    log.info("GET %s params=%s", path, params)
    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"TheMealDB request failed: {exc}") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("TheMealDB returned invalid JSON") from exc
    return payload.get("meals")


def _details(meal: dict) -> dict:
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": (meal.get(f"strMeasure{i}") or "").strip()})
    return {
        "id": meal["idMeal"], "name": meal["strMeal"], "category": meal.get("strCategory"),
        "area": meal.get("strArea"), "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"), "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"), "ingredients": ingredients,
    }


@mcp.tool()
def search_meals_by_name(query: str, limit: Annotated[int, Field(ge=1, le=25)] = 5) -> Any:
    """Search meals by name (e.g. "Arrabiata"). Returns up to `limit` meals with id, name, area, category, thumb."""
    meals = _get("search.php", s=query)
    if not meals:
        return NO_MATCHES
    return [{"id": m["idMeal"], "name": m["strMeal"], "area": m.get("strArea"),
             "category": m.get("strCategory"), "thumb": m.get("strMealThumb")} for m in meals[:limit]]


@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: Annotated[int, Field(ge=1, le=25)] = 12) -> Any:
    """List meals that use a main ingredient (e.g. "chicken"). Returns small cards: id, name, thumb."""
    meals = _get("filter.php", i=ingredient)
    if not meals:
        return NO_MATCHES
    return [{"id": m["idMeal"], "name": m["strMeal"], "thumb": m.get("strMealThumb")} for m in meals[:limit]]


@mcp.tool()
def random_meal() -> Any:
    """Look up one random meal. Same shape as meal_details."""
    meals = _get("random.php")
    if not meals:
        return NO_MATCHES
    return _details(meals[0])


@mcp.tool()
def meal_details(id: str | int) -> Any:
    """Full recipe for a meal id (e.g. 52771): instructions, image, source, youtube, ingredients with measures."""
    meals = _get("lookup.php", i=str(id))
    if not meals:
        return NO_MATCHES
    return _details(meals[0])


if __name__ == "__main__":
    mcp.run(transport="stdio")
