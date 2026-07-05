import json
import os
from typing import Any

# Resolve data paths relative to the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_PATH = os.path.join(BASE_DIR, "data", "recipes.json")
NUTRITION_PATH = os.path.join(BASE_DIR, "data", "nutrition.json")


def load_recipes() -> list[dict[str, Any]]:
    """Helper to load recipes database from local JSON file."""
    if not os.path.exists(RECIPES_PATH):
        raise FileNotFoundError(f"Recipes database file not found at {RECIPES_PATH}")
    with open(RECIPES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_nutrition() -> dict[str, dict[str, Any]]:
    """Helper to load nutrition database from local JSON file."""
    if not os.path.exists(NUTRITION_PATH):
        raise FileNotFoundError(
            f"Nutrition database file not found at {NUTRITION_PATH}"
        )
    with open(NUTRITION_PATH, encoding="utf-8") as f:
        return json.load(f)


# Tool 1: search_recipe
async def search_recipe(ingredients: list[str]) -> dict[str, Any]:
    """Search for the best matching recipe based on the list of pantry ingredients.

    Args:
        ingredients: A list of ingredient names currently available in the pantry.

    Returns:
        A dictionary containing the best matching recipe name, matched ingredients list,
        and match score.
    """
    # Reject empty inputs
    if not ingredients:
        return {"error": "Input ingredient list cannot be empty", "match_score": 0}

    # Filter and clean ingredient input
    clean_pantry = [ing.strip().lower() for ing in ingredients if ing.strip()]
    if not clean_pantry:
        return {
            "error": "Input ingredient list contains no valid ingredients",
            "match_score": 0,
        }

    try:
        recipes = load_recipes()
    except Exception as e:
        return {"error": f"Failed to load recipe data: {e!s}", "match_score": 0}

    best_recipe = None
    best_score = -1
    best_matched_ingredients: list[str] = []

    # Iterate through recipes to find the one with the highest ingredient overlap
    for recipe in recipes:
        recipe_ings = recipe.get("ingredients", [])
        matched = []

        # Compare pantry ingredients against recipe ingredients (substring matching)
        for r_ing in recipe_ings:
            norm_r_ing = r_ing.strip().lower()
            for p_ing in clean_pantry:
                if p_ing in norm_r_ing or norm_r_ing in p_ing:
                    matched.append(r_ing)
                    break

        score = len(matched)
        if score > best_score:
            best_score = score
            best_recipe = recipe
            best_matched_ingredients = matched

    if best_recipe is None or best_score <= 0:
        return {
            "recipe_name": "No matching recipe found",
            "match_score": 0,
            "matched_ingredients": [],
        }

    return {
        "recipe_name": best_recipe.get("name"),
        "match_score": best_score,
        "matched_ingredients": best_matched_ingredients,
    }


# Tool 2: get_nutrition
async def get_nutrition(recipe_name: str) -> dict[str, Any]:
    """Retrieve the nutritional profile for a specified recipe name.

    Args:
        recipe_name: The exact name of the recipe to query.

    Returns:
        A dictionary containing the nutritional profile: serving_size, calories,
        protein, carbs, and fat.
    """
    # Reject empty inputs
    if not recipe_name or not recipe_name.strip():
        return {"error": "Recipe name cannot be empty"}

    try:
        nutrition_db = load_nutrition()
    except Exception as e:
        return {"error": f"Failed to load nutrition data: {e!s}"}

    # Case-insensitive exact match
    target_key = recipe_name.strip().lower()
    for name, profile in nutrition_db.items():
        if name.strip().lower() == target_key:
            return {
                "calories": profile.get("calories", 0),
                "protein": profile.get("protein", "0g"),
                "carbs": profile.get("carbs", "0g"),
                "fat": profile.get("fat", "0g"),
                "serving_size": profile.get("serving_size", "unknown"),
            }

    return {"error": f"Recipe '{recipe_name}' not found in the nutrition database"}


# Tool 3: find_missing_ingredients
async def find_missing_ingredients(
    recipe_name: str, pantry_ingredients: list[str]
) -> dict[str, Any]:
    """Compare a recipe's required ingredients against pantry ingredients to find what's missing.

    Args:
        recipe_name: The name of the recipe to check.
        pantry_ingredients: The list of ingredients currently available in the pantry.

    Returns:
        A dictionary containing the list of missing ingredients and the full required
        recipe ingredients list.
    """
    # Reject empty inputs
    if not recipe_name or not recipe_name.strip():
        return {"error": "Recipe name cannot be empty"}

    try:
        recipes = load_recipes()
    except Exception as e:
        return {"error": f"Failed to load recipe data: {e!s}"}

    # Find the recipe by name (case-insensitive)
    target_recipe = None
    target_name_lower = recipe_name.strip().lower()
    for recipe in recipes:
        if recipe.get("name", "").strip().lower() == target_name_lower:
            target_recipe = recipe
            break

    if not target_recipe:
        return {"error": f"Recipe '{recipe_name}' not found"}

    required_ingredients = target_recipe.get("ingredients", [])
    clean_pantry = [ing.strip().lower() for ing in pantry_ingredients if ing.strip()]
    missing = []

    # Find missing ingredients
    for req_ing in required_ingredients:
        norm_req_ing = req_ing.strip().lower()
        matched = False
        for p_ing in clean_pantry:
            if p_ing in norm_req_ing or norm_req_ing in p_ing:
                matched = True
                break
        if not matched:
            missing.append(req_ing)

    return {
        "missing_ingredients": missing,
        "required_ingredients": required_ingredients,
    }
