import json

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import pantry_agent


@pytest.mark.asyncio
async def test_pantry_agent_normal_flow() -> None:
    # Set up the runner
    runner = InMemoryRunner(agent=pantry_agent, app_name="app")
    runner.auto_create_session = True

    # Inputs with duplicates, varying case, extra spaces, commas, and newlines
    raw_input = "  Chicken , quinoa  , spinach, chicken\n; garlic ; spinach "
    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=raw_input)]
    )

    events = []
    async for event in runner.run_async(
        user_id="test_user",
        session_id="test_session",
        new_message=new_message,
    ):
        events.append(event)

    # We expect one final event containing the PantryAgent's structured output
    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None
    assert len(final_event.content.parts) > 0

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)
    assert "ingredients" in data
    # Case should be lowered, whitespaces stripped, order preserved, duplicates removed
    assert data["ingredients"] == ["chicken", "quinoa", "spinach", "garlic"]
    assert data["count"] == 4


@pytest.mark.asyncio
async def test_pantry_agent_empty_validation() -> None:
    runner = InMemoryRunner(agent=pantry_agent, app_name="app")
    runner.auto_create_session = True

    # Empty string input
    new_message = types.Content(role="user", parts=[types.Part.from_text(text="   ")])

    events = []
    async for event in runner.run_async(
        user_id="test_user",
        session_id="test_session_empty",
        new_message=new_message,
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None
    assert len(final_event.content.parts) > 0

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)
    assert "error" in data
    assert data["ingredients"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_pantry_agent_no_tokens_validation() -> None:
    runner = InMemoryRunner(agent=pantry_agent, app_name="app")
    runner.auto_create_session = True

    # Input containing only commas and spaces (no valid alphanumeric tokens)
    new_message = types.Content(
        role="user", parts=[types.Part.from_text(text=" , , ,, ; \n ")]
    )

    events = []
    async for event in runner.run_async(
        user_id="test_user",
        session_id="test_session_no_tokens",
        new_message=new_message,
    ):
        events.append(event)

    assert len(events) > 0
    final_event = events[-1]
    assert final_event.content is not None
    assert final_event.content.parts is not None
    assert len(final_event.content.parts) > 0

    text = final_event.content.parts[0].text
    assert text is not None
    data = json.loads(text)
    assert "error" in data
    assert data["ingredients"] == []
    assert data["count"] == 0
