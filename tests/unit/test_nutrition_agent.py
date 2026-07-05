import json

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import nutrition_agent


@pytest.mark.asyncio
async def test_nutrition_agent_normal_flow() -> None:
    runner = InMemoryRunner(agent=nutrition_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_nutrition"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run agent - it will pull recipe name from state_delta
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"recipe": "Grilled Chicken Quinoa Bowl"},
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Check state was updated with "nutrition"
    updated_session = await runner.session_service.get_session(
        app_name="app", user_id=user_id, session_id=session_id
    )
    assert updated_session is not None
    assert updated_session.state.get("nutrition") == {
        "calories": 520,
        "protein": 45,
        "carbs": 40,
        "fat": 18,
        "serving_size": "450g",
    }

    # Check return structure
    assert data["calories"] == 520
    assert data["protein"] == 45
    assert data["serving_size"] == "450g"


@pytest.mark.asyncio
async def test_nutrition_agent_missing_recipe_error() -> None:
    runner = InMemoryRunner(agent=nutrition_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_nutrition_empty"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run without providing "recipe" in state
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"recipe": None},
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Verify structured error response
    assert "error" in data
    assert "calories" not in data


@pytest.mark.asyncio
async def test_nutrition_agent_not_found_in_db_error() -> None:
    runner = InMemoryRunner(agent=nutrition_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_nutrition_not_found"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run with a recipe not present in the DB
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"recipe": "Nonexistent Recipe"},
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Verify structured error response from database lookup
    assert "error" in data
    assert "calories" not in data
