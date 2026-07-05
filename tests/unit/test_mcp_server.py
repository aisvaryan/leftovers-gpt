import pytest

from mcp_server.tools import find_missing_ingredients, get_nutrition, search_recipe


@pytest.mark.asyncio
async def test_search_recipe() -> None:
    # Test valid input matching "Grilled Chicken Quinoa Bowl"
    res = await search_recipe(["chicken", "quinoa", "spinach", "garlic"])
    assert "error" not in res
    assert res["recipe_name"] == "Grilled Chicken Quinoa Bowl"
    assert res["match_score"] == 4
    assert "chicken" in res["matched_ingredients"]

    # Test empty input error handling
    err_res = await search_recipe([])
    assert "error" in err_res


@pytest.mark.asyncio
async def test_get_nutrition() -> None:
    # Test valid exact case lookup
    res = await get_nutrition("Grilled Chicken Quinoa Bowl")
    assert "error" not in res
    assert res["calories"] == 520
    assert res["protein"] == 45
    assert res["serving_size"] == "450g"

    # Test case insensitivity
    res_lower = await get_nutrition("grilled chicken quinoa bowl")
    assert "error" not in res_lower
    assert res_lower["calories"] == 520

    # Test missing recipe error handling
    err_res = await get_nutrition("Nonexistent Recipe")
    assert "error" in err_res


@pytest.mark.asyncio
async def test_find_missing_ingredients() -> None:
    # Test partial list matching "Grilled Chicken Quinoa Bowl"
    # Requires: chicken, quinoa, spinach, olive oil, garlic.
    # Provided: chicken, quinoa, spinach
    res = await find_missing_ingredients(
        "Grilled Chicken Quinoa Bowl", ["chicken", "quinoa", "spinach"]
    )
    assert "error" not in res
    assert "olive oil" in res["missing_ingredients"]
    assert "garlic" in res["missing_ingredients"]
    assert "chicken" not in res["missing_ingredients"]
    assert len(res["required_ingredients"]) == 5

    # Test missing recipe name error handling
    err_res = await find_missing_ingredients("Nonexistent Recipe", ["chicken"])
    assert "error" in err_res
