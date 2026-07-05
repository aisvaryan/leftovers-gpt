import json
from unittest.mock import patch

import pytest
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import NutritionAgent, coordinator_agent


@pytest.mark.asyncio
async def test_coordinator_normal_flow() -> None:
    runner = InMemoryRunner(agent=coordinator_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_coordinator_normal"

    new_message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text="  Chicken , quinoa  , spinach, chicken ; garlic "
            )
        ],
    )

    events = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Output structure must match final assembled output
    assert "ingredients" in data
    assert "recipe" in data
    assert "nutrition" in data
    assert "shopping" in data

    assert data["ingredients"] == ["chicken", "quinoa", "spinach", "garlic"]
    assert data["recipe"] == "Grilled Chicken Quinoa Bowl"
    assert data["nutrition"]["calories"] == 520
    assert data["shopping"]["missing_ingredients"] == ["olive oil"]


@pytest.mark.asyncio
async def test_coordinator_pantry_failure() -> None:
    runner = InMemoryRunner(agent=coordinator_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_coordinator_pantry_fail"

    # Empty inputs trigger PantryAgent failure
    new_message = types.Content(role="user", parts=[types.Part.from_text(text="   ")])

    events = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)

    # Execution should halt immediately and output state (which is empty)
    assert data["ingredients"] is None
    assert data["recipe"] is None


@pytest.mark.asyncio
async def test_coordinator_nutrition_partial_failure() -> None:
    runner = InMemoryRunner(agent=coordinator_agent, app_name="app")
    runner.auto_create_session = True

    user_id = "test_user"
    session_id = "test_session_coordinator_nutrition_fail"

    new_message = types.Content(
        role="user",
        parts=[
            types.Part.from_text(
                text="  Chicken , quinoa  , spinach, chicken ; garlic "
            )
        ],
    )

    # Mock NutritionAgent.run_async at class level to simulate failure
    async def mock_run(ctx):
        yield Event(
            author="nutrition_agent",
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text='{"error": "Simulated nutrition error"}')
                ],
            ),
            actions=EventActions(state_delta={"nutrition": None}),
        )

    with patch.object(NutritionAgent, "run_async", side_effect=mock_run):
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            events.append(event)

        assert len(events) > 0
        final_event = events[-1]
        text = final_event.content.parts[0].text
        assert text is not None
        data = json.loads(text)

        # Nutrition should be None due to mock failure, but Shopping list should still run
        assert data["recipe"] == "Grilled Chicken Quinoa Bowl"
        assert data["nutrition"] is None
        assert data["shopping"] is not None
        assert data["shopping"]["missing_ingredients"] == ["olive oil"]
