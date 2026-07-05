import json

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import shopping_agent


@pytest.mark.asyncio
async def test_shopping_agent_normal_flow() -> None:
    runner = InMemoryRunner(agent=shopping_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_shopping"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run agent - it will pull recipe and ingredients from state_delta
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={
            "recipe": "Grilled Chicken Quinoa Bowl",
            "ingredients": ["chicken", "quinoa"],
        },
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Check state was updated with "shopping"
    updated_session = await runner.session_service.get_session(
        app_name="app", user_id=user_id, session_id=session_id
    )
    assert updated_session is not None
    assert updated_session.state.get("shopping") == {
        "missing_ingredients": ["spinach", "olive oil", "garlic"],
        "required_ingredients": [
            "chicken",
            "quinoa",
            "spinach",
            "olive oil",
            "garlic",
        ],
    }

    # Check return structure
    assert data["missing_ingredients"] == ["spinach", "olive oil", "garlic"]
    assert data["required_ingredients"] == [
        "chicken",
        "quinoa",
        "spinach",
        "olive oil",
        "garlic",
    ]


@pytest.mark.asyncio
async def test_shopping_agent_missing_recipe_error() -> None:
    runner = InMemoryRunner(agent=shopping_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_shopping_empty"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run without recipe name
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"recipe": None, "ingredients": []},
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
    assert "missing_ingredients" not in data


@pytest.mark.asyncio
async def test_shopping_agent_not_found_in_db_error() -> None:
    runner = InMemoryRunner(agent=shopping_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_shopping_not_found"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run with a nonexistent recipe name
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"recipe": "Nonexistent Recipe", "ingredients": []},
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
    assert "missing_ingredients" not in data
