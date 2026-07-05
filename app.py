#!/usr/bin/env python3
import asyncio
import json
import uuid

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as adk_app


async def run_leftovers_gpt(user_input: str):
    """Run the LeftoversGPT agent with the provided user input."""
    # Initialize the local in-memory runner
    runner = InMemoryRunner(
        agent=adk_app.root_agent,
        app_name=adk_app.name,
    )
    # Enable automatic session creation for this runner
    runner.auto_create_session = True

    session_id = f"leftovers_{uuid.uuid4().hex[:8]}"

    print("\n--- LeftoversGPT Session Started ---")
    print(f"Input ingredients: {user_input}")
    print("Processing...\n")
    print("-----------------------------------")

    # Construct the user message using google-genai types
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_input)],
    )

    # Run the coordinator agent and stream/print the output events
    try:
        async for event in runner.run_async(
            user_id="local_developer",
            session_id=session_id,
            new_message=new_message,
        ):
            # Format and print the event contents clearly
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        # Extract final aggregated output from the coordinator agent
                        if event.author == "coordinator_agent" and not event.partial:
                            try:
                                data = json.loads(part.text)
                                if all(
                                    k in data
                                    for k in [
                                        "ingredients",
                                        "recipe",
                                        "nutrition",
                                        "shopping",
                                    ]
                                ):
                                    print("\n=== Final Meal Plan ===")
                                    print(
                                        f"Parsed Ingredients: {data.get('ingredients')}"
                                    )
                                    print(f"Recipe Match: {data.get('recipe')}")
                                    print("Nutrition Profile:")
                                    nut = data.get("nutrition")
                                    if isinstance(nut, dict):
                                        for k, v in nut.items():
                                            print(f"  - {k}: {v}")
                                    else:
                                        print("  - N/A")
                                    print("Shopping / Missing Ingredients:")
                                    shop = data.get("shopping")
                                    if isinstance(shop, dict):
                                        print(
                                            f"  - Missing: {shop.get('missing_ingredients')}"
                                        )
                                        print(
                                            f"  - Required: {shop.get('required_ingredients')}"
                                        )
                                    else:
                                        print("  - N/A")
                                    print("=======================\n")
                                else:
                                    print(f"[{event.author}]: {part.text.strip()}")
                            except Exception:
                                print(f"[{event.author}]: {part.text.strip()}")
                        else:
                            # Show progress/output of step-wise agents
                            print(f"[{event.author}]: {part.text.strip()}")

    except Exception as e:
        print(f"\nError running LeftoversGPT: {e}")

    print("\n-----------------------------------")
    print("--- Session Finished ---\n")


def main():
    print("\nLeftoversGPT (Multi-Agent System)")
    print("Type 'exit' to quit\n")

    while True:
        try:
            user_input = input("Enter leftovers: ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if user_input.lower().strip() == "exit":
            print("\nGoodbye!")
            break

        asyncio.run(run_leftovers_gpt(user_input))


if __name__ == "__main__":
    main()
