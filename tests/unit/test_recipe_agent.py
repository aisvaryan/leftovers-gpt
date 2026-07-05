import json

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import recipe_agent


@pytest.mark.asyncio
async def test_recipe_agent_normal_flow() -> None:
    # Set up runner
    runner = InMemoryRunner(agent=recipe_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_recipe"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    # Run agent - it will pull ingredients from state (passed via state_delta)
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"ingredients": ["chicken", "quinoa", "spinach", "garlic"]},
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Print for debugging
    print("DATA RETURNED IN NORMAL FLOW:", data)

    # Check state was updated with "recipe"
    updated_session = await runner.session_service.get_session(
        app_name="app", user_id=user_id, session_id=session_id
    )
    assert updated_session is not None
    print("SESSION STATE:", updated_session.state)
    assert updated_session.state.get("recipe") == "Grilled Chicken Quinoa Bowl"

    # Check return structure
    assert data["recipe_name"] == "Grilled Chicken Quinoa Bowl"
    assert data["match_score"] == 4


@pytest.mark.asyncio
async def test_recipe_agent_missing_ingredients_error() -> None:
    runner = InMemoryRunner(agent=recipe_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_recipe_empty"

    new_message = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    events = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
        state_delta={"ingredients": []},
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
    assert "ingredients" not in data
