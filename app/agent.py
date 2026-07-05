# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import re
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps import App
from google.adk.events import Event, EventActions
from google.adk.models import Gemini
from google.genai import types
from pydantic import PrivateAttr

from app.tools import get_mcp_toolset

# Model selection - defaults to gemini-2.5-flash
# Allow configuration via environment variables
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

model_instance = Gemini(
    model=MODEL_NAME,
    retry_options=types.HttpRetryOptions(attempts=3),
)


class PantryAgent(BaseAgent):
    """Deterministic agent responsible for input normalization, cleaning, and validation of ingredients."""

    def __init__(self) -> None:
        super().__init__(
            name="pantry_agent",
            description="Normalizes raw input ingredients into a structured list.",
        )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Extract user input from user_content or session events
        user_input = ""
        if ctx.user_content and ctx.user_content.parts:
            parts_text = [p.text for p in ctx.user_content.parts if p.text]
            user_input = " ".join(parts_text)

        if not user_input and ctx.session.events:
            for event in reversed(ctx.session.events):
                if event.author == "user" and event.content:
                    user_input = event.content
                    break

        # Validate: reject empty input
        if not user_input or not user_input.strip():
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=json.dumps(
                                {
                                    "error": "Input ingredient list cannot be empty",
                                    "ingredients": [],
                                    "count": 0,
                                }
                            )
                        )
                    ],
                ),
            )
            return

        # Split into list of ingredients by common delimiters (commas, newlines, semicolons)
        user_input_str = str(user_input) if user_input else ""
        raw_items = re.split(r"[,\n;]+", user_input_str)

        # Normalize: lowercase, strip whitespace, remove extra spaces
        ingredients = []
        seen = set()
        for item in raw_items:
            # Normalize internal spacing and lowercase
            cleaned = " ".join(item.strip().lower().split())

            # Validate: reject empty or invalid token (must contain alphanumeric)
            if cleaned and re.search(r"[a-zA-Z0-9]", cleaned):
                if cleaned not in seen:
                    seen.add(cleaned)
                    ingredients.append(cleaned)

        # Validate: reject inputs with no valid tokens
        if not ingredients:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=json.dumps(
                                {
                                    "error": "Input contains no valid ingredient tokens",
                                    "ingredients": [],
                                    "count": 0,
                                }
                            )
                        )
                    ],
                ),
            )
            return

        output = {"ingredients": ingredients, "count": len(ingredients)}

        # Save results in the session state for downstream agents
        ctx.session.state["ingredients"] = ingredients
        ctx.session.state["pantry_ingredients"] = ingredients
        ctx.session.state["pantry_count"] = len(ingredients)

        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=json.dumps(output))],
            ),
        )


# 1. PantryAgent
pantry_agent = PantryAgent()


class RecipeAgent(BaseAgent):
    """MCP-powered agent that determines the best matching recipe.

    Why MCP is used instead of local logic:
    Decoupling the recipe search and scoring logic into an external MCP tool allows the
    data layer (JSON/DB files and algorithms) to scale and change independently without
    requiring modifications to the agent application logic.

    How agent state flows from PantryAgent:
    PantryAgent processes raw user input and persists the clean ingredient list in the
    session state under `ctx.session.state["ingredients"]`. RecipeAgent reads this list directly,
    establishing a clean, state-driven pipeline between the agents.
    """

    _toolset: Any = PrivateAttr(default=None)

    def __init__(self) -> None:
        super().__init__(
            name="recipe_agent",
            description="Determines the best matching recipe based on available ingredients.",
        )
        self._toolset = get_mcp_toolset("search_recipe")

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. State flow from PantryAgent: Read clean ingredients from ctx.session.state["ingredients"]
        ingredients = ctx.session.state.get("ingredients", [])

        # Validate ingredient list
        if not ingredients:
            err_output = {"error": "No ingredients found in session state"}
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
            )
            return

        # 2. Call MCP tool: search_recipe ONLY via McpToolset
        try:
            tools = await self._toolset.get_tools(ctx)
            search_tool = next((t for t in tools if t.name == "search_recipe"), None)

            if not search_tool:
                raise ValueError("search_recipe tool not found in toolset")

            # Execute tool run_async
            result = await search_tool.run_async(
                args={"ingredients": ingredients},
                tool_context=ctx,
            )

            # Handle MCP failures gracefully
            if not isinstance(result, dict) or result.get("isError"):
                err_msg = (
                    result.get("content", [{}])[0].get("text", "Unknown MCP tool error")
                    if isinstance(result, dict)
                    else str(result)
                )
                err_output = {"error": f"MCP tool execution failed: {err_msg}"}
                ctx.session.state["recipe"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(err_output))],
                    ),
                    actions=EventActions(state_delta={"recipe": None}),
                )
                return

            # Extract structured recipe output
            structured_content = result.get("structuredContent")
            recipe_name = None
            output_data = {}

            if isinstance(structured_content, dict):
                output_data = structured_content
                recipe_name = structured_content.get("recipe_name")
            else:
                try:
                    content_text = result.get("content", [{}])[0].get("text", "")
                    output_data = json.loads(content_text)
                    recipe_name = output_data.get("recipe_name")
                except Exception:
                    pass

            if not recipe_name:
                err_output = {
                    "error": "Recipe matching tool did not return a valid recipe"
                }
                ctx.session.state["recipe"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(err_output))],
                    ),
                    actions=EventActions(state_delta={"recipe": None}),
                )
                return

            # Store selected recipe name in state under "recipe"
            ctx.session.state["recipe"] = recipe_name

            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(output_data))],
                ),
                actions=EventActions(state_delta={"recipe": recipe_name}),
            )

        except Exception as e:
            # Handle unexpected tool/connection failures gracefully
            err_output = {"error": f"MCP Tool execution failed: {e!s}"}
            ctx.session.state["recipe"] = None
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
                actions=EventActions(state_delta={"recipe": None}),
            )


# 2. RecipeAgent
recipe_agent = RecipeAgent()


class NutritionAgent(BaseAgent):
    """MCP-powered agent that retrieves nutritional information for a selected recipe.

    Why MCP is used instead of local logic (Separation of Concerns):
    By querying an external MCP server for recipe nutrition profiles, the agent avoids
    having to store, parse, or query local database files (nutrition.json) directly. This
    keeps the agent code lightweight, modular, and independent of backend data structures.

    How agent state flows:
    RecipeAgent writes the matched recipe name to `ctx.session.state["recipe"]`. NutritionAgent
    reads this value, invokes the MCP `get_nutrition` tool, and saves the retrieved profile
    to `ctx.session.state["nutrition"]`.
    """

    _toolset: Any = PrivateAttr(default=None)

    def __init__(self) -> None:
        super().__init__(
            name="nutrition_agent",
            description="Retrieves the nutritional profile for a specified recipe name.",
        )
        self._toolset = get_mcp_toolset("get_nutrition")

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. State flow: Retrieve matched recipe name from state
        recipe_name = ctx.session.state.get("recipe")

        # Validate recipe name is present
        if not recipe_name:
            err_output = {
                "error": "No recipe name found in session state to look up nutrition"
            }
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
                actions=EventActions(state_delta={"nutrition": None}),
            )
            return

        # 2. Call MCP tool: get_nutrition ONLY
        try:
            tools = await self._toolset.get_tools(ctx)
            nutrition_tool = next((t for t in tools if t.name == "get_nutrition"), None)

            if not nutrition_tool:
                raise ValueError("get_nutrition tool not found in toolset")

            # Execute tool run_async
            result = await nutrition_tool.run_async(
                args={"recipe_name": recipe_name},
                tool_context=ctx,
            )

            # Handle MCP failures gracefully
            if not isinstance(result, dict) or result.get("isError"):
                err_msg = (
                    result.get("content", [{}])[0].get("text", "Unknown MCP tool error")
                    if isinstance(result, dict)
                    else str(result)
                )
                err_output = {"error": f"MCP tool execution failed: {err_msg}"}
                ctx.session.state["nutrition"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(err_output))],
                    ),
                    actions=EventActions(state_delta={"nutrition": None}),
                )
                return

            # Extract structured nutrition output
            structured_content = result.get("structuredContent")
            nutrition_data = {}

            if isinstance(structured_content, dict):
                nutrition_data = structured_content
            else:
                try:
                    content_text = result.get("content", [{}])[0].get("text", "")
                    nutrition_data = json.loads(content_text)
                except Exception:
                    pass

            if "error" in nutrition_data:
                # Handle gracefully when recipe not found in DB
                ctx.session.state["nutrition"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(nutrition_data))],
                    ),
                    actions=EventActions(state_delta={"nutrition": None}),
                )
                return

            # Store nutritional profile in session state under "nutrition"
            ctx.session.state["nutrition"] = nutrition_data

            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(nutrition_data))],
                ),
                actions=EventActions(state_delta={"nutrition": nutrition_data}),
            )

        except Exception as e:
            # Handle unexpected failures gracefully
            err_output = {"error": f"MCP Tool execution failed: {e!s}"}
            ctx.session.state["nutrition"] = None
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
                actions=EventActions(state_delta={"nutrition": None}),
            )


# 3. NutritionAgent
nutrition_agent = NutritionAgent()


class ShoppingAgent(BaseAgent):
    """MCP-powered agent that computes missing ingredients needed to complete a recipe.

    Why MCP is used instead of local logic (Separation of Concerns):
    By delegating the ingredients comparison and set difference calculations to the MCP
    `find_missing_ingredients` tool, the agent does not need to know about recipe data
    structures or local database storage (recipes.json). This guarantees data encapsulation
    and keeps the agent's logic focused strictly on coordination.

    How agent state flows:
    ShoppingAgent consumes `ctx.session.state["recipe"]` (set by RecipeAgent) and
    `ctx.session.state["ingredients"]` (set by PantryAgent), executes the comparison via MCP,
    and stores the missing ingredients result in `ctx.session.state["shopping"]`.
    """

    _toolset: Any = PrivateAttr(default=None)

    def __init__(self) -> None:
        super().__init__(
            name="shopping_agent",
            description="Computes missing ingredients needed to complete a recipe.",
        )
        self._toolset = get_mcp_toolset("find_missing_ingredients")

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # 1. State flow: Retrieve recipe name and pantry ingredients from state
        recipe_name = ctx.session.state.get("recipe")
        ingredients = ctx.session.state.get("ingredients", [])

        # Validate inputs
        if not recipe_name:
            err_output = {
                "error": "No recipe name found in session state to compute shopping list"
            }
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
                actions=EventActions(state_delta={"shopping": None}),
            )
            return

        # 2. Call MCP tool: find_missing_ingredients ONLY
        try:
            tools = await self._toolset.get_tools(ctx)
            shopping_tool = next(
                (t for t in tools if t.name == "find_missing_ingredients"), None
            )

            if not shopping_tool:
                raise ValueError("find_missing_ingredients tool not found in toolset")

            # Execute tool run_async
            result = await shopping_tool.run_async(
                args={
                    "recipe_name": recipe_name,
                    "pantry_ingredients": ingredients,
                },
                tool_context=ctx,
            )

            # Handle MCP failures gracefully
            if not isinstance(result, dict) or result.get("isError"):
                err_msg = (
                    result.get("content", [{}])[0].get("text", "Unknown MCP tool error")
                    if isinstance(result, dict)
                    else str(result)
                )
                err_output = {"error": f"MCP tool execution failed: {err_msg}"}
                ctx.session.state["shopping"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(err_output))],
                    ),
                    actions=EventActions(state_delta={"shopping": None}),
                )
                return

            # Extract structured shopping output
            structured_content = result.get("structuredContent")
            shopping_data = {}

            if isinstance(structured_content, dict):
                shopping_data = structured_content
            else:
                try:
                    content_text = result.get("content", [{}])[0].get("text", "")
                    shopping_data = json.loads(content_text)
                except Exception:
                    pass

            if "error" in shopping_data:
                # Handle gracefully when recipe not found in DB
                ctx.session.state["shopping"] = None
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=json.dumps(shopping_data))],
                    ),
                    actions=EventActions(state_delta={"shopping": None}),
                )
                return

            # Store shopping output in session state under "shopping"
            ctx.session.state["shopping"] = shopping_data

            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(shopping_data))],
                ),
                actions=EventActions(state_delta={"shopping": shopping_data}),
            )

        except Exception as e:
            # Handle unexpected failures gracefully
            err_output = {"error": f"MCP Tool execution failed: {e!s}"}
            ctx.session.state["shopping"] = None
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps(err_output))],
                ),
                actions=EventActions(state_delta={"shopping": None}),
            )


# 4. ShoppingAgent
shopping_agent = ShoppingAgent()


class CoordinatorAgent(BaseAgent):
    """Pipeline orchestrator for LeftoversGPT that sequentially executes the sub-agents.

    Orchestration Role vs Agent Responsibilities:
    The CoordinatorAgent acts strictly as a control-flow manager. It determines the sequence of
    execution, handles error propagation, and enforces failure/recovery policies. The individual
    sub-agents (PantryAgent, RecipeAgent, NutritionAgent, ShoppingAgent) are responsible for
    executing their specific functional domains.

    Why the Coordinator Must Remain Logic-Free:
    To preserve a clean separation of concerns and prevent logic duplication, the Coordinator
    must not perform any data processing, scoring, comparison, or direct MCP queries. It only
    drives the execution loop and aggregates the final output.

    State Flow Across the Pipeline:
    State is passed strictly through `ctx.session.state`. Each agent reads its required inputs
    from this shared state and publishes its results there:
    1. PantryAgent writes clean ingredients to `state["ingredients"]`.
    2. RecipeAgent reads `state["ingredients"]` and writes the matched recipe to `state["recipe"]`.
    3. NutritionAgent reads `state["recipe"]` and writes nutrition info to `state["nutrition"]`.
    4. ShoppingAgent reads `state["recipe"]` and `state["ingredients"]` and writes to `state["shopping"]`.
    """

    def __init__(self) -> None:
        super().__init__(
            name="coordinator_agent",
            description="Orchestrates the leftovers-gpt workflow by running step agents sequentially.",
            sub_agents=[pantry_agent, recipe_agent, nutrition_agent, shopping_agent],
        )

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        # Helper to construct final aggregated output
        def build_final_output() -> str:
            return json.dumps(
                {
                    "ingredients": ctx.session.state.get("ingredients"),
                    "recipe": ctx.session.state.get("recipe"),
                    "nutrition": ctx.session.state.get("nutrition"),
                    "shopping": ctx.session.state.get("shopping"),
                }
            )

        # 1. PantryAgent
        pantry_failed = False
        async for event in pantry_agent.run_async(ctx):
            yield event
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        try:
                            data = json.loads(part.text)
                            if "error" in data:
                                pantry_failed = True
                        except Exception:
                            pass

        if pantry_failed:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=build_final_output())],
                ),
            )
            return

        # 2. RecipeAgent
        recipe_failed = False
        async for event in recipe_agent.run_async(ctx):
            yield event
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        try:
                            data = json.loads(part.text)
                            if "error" in data:
                                recipe_failed = True
                        except Exception:
                            pass

        if recipe_failed:
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=build_final_output())],
                ),
            )
            return

        # 3. NutritionAgent (failure does not stop execution)
        async for event in nutrition_agent.run_async(ctx):
            yield event

        # 4. ShoppingAgent
        async for event in shopping_agent.run_async(ctx):
            yield event

        # Yield the final aggregated output
        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=build_final_output())],
            ),
        )


# 5. CoordinatorAgent
coordinator_agent = CoordinatorAgent()

root_agent = coordinator_agent

# App entry definition
app = App(
    root_agent=root_agent,
    name="app",
)
