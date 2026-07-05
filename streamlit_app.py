import asyncio
import json
import uuid

import streamlit as st
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import app as adk_app


async def run_agent(user_input, status_container, result_container):
    # Initialize the local in-memory runner
    runner = InMemoryRunner(
        agent=adk_app.root_agent,
        app_name=adk_app.name,
    )
    # Enable automatic session creation to prevent SessionNotFoundError
    runner.auto_create_session = True

    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_input)],
    )

    session_id = f"session_{uuid.uuid4().hex[:8]}"

    try:
        async for event in runner.run_async(
            user_id="web_user",
            session_id=session_id,
            new_message=new_message,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        # Log intermediate steps to help the user track execution
                        status_container.write(
                            f"🤖 **{event.author}** is processing..."
                        )

                        # Final aggregated response handling
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
                                    with result_container:
                                        st.success(
                                            "🎉 Meal Plan Generated Successfully!"
                                        )

                                        st.markdown("### 🥗 Parsed Ingredients")
                                        st.write(
                                            ", ".join(data.get("ingredients") or [])
                                        )

                                        st.markdown(
                                            f"### 🍽️ Recipe: **{data.get('recipe')}**"
                                        )

                                        # Display Nutrition in metric columns
                                        st.markdown("#### ⚡ Nutrition Profile")
                                        nut = data.get("nutrition")
                                        if isinstance(nut, dict):
                                            cols = st.columns(5)
                                            cols[0].metric(
                                                "Serving Size",
                                                nut.get("serving_size", "N/A"),
                                            )
                                            cols[1].metric(
                                                "Calories",
                                                f"{nut.get('calories', 0)} kcal",
                                            )
                                            cols[2].metric(
                                                "Protein",
                                                f"{nut.get('protein', 0)}g",
                                            )
                                            cols[3].metric(
                                                "Carbs",
                                                f"{nut.get('carbs', 0)}g",
                                            )
                                            cols[4].metric(
                                                "Fat", f"{nut.get('fat', 0)}g"
                                            )
                                        else:
                                            st.info("Nutrition profile not available.")

                                        # Display shopping list split by missing/required
                                        st.markdown("#### 🛒 Shopping List Details")
                                        shop = data.get("shopping")
                                        if isinstance(shop, dict):
                                            missing = (
                                                shop.get("missing_ingredients") or []
                                            )
                                            required = (
                                                shop.get("required_ingredients") or []
                                            )

                                            col_shop1, col_shop2 = st.columns(2)
                                            with col_shop1:
                                                st.markdown("**Missing Ingredients:**")
                                                if missing:
                                                    for item in missing:
                                                        st.markdown(f"- ❌ {item}")
                                                else:
                                                    st.markdown(
                                                        "- ✅ None! You have everything."
                                                    )
                                            with col_shop2:
                                                st.markdown(
                                                    "**All Required Ingredients:**"
                                                )
                                                for item in required:
                                                    st.markdown(f"- {item}")
                                        else:
                                            st.info("Shopping list not available.")
                                else:
                                    # Fallback to plain rendering if structure differs
                                    result_container.json(data)
                            except Exception:
                                result_container.text(part.text)
    except Exception as e:
        status_container.error(f"Error running pipeline: {e}")


# Streamlit layout configuration
st.set_page_config(page_title="LeftoversGPT", page_icon="🥗", layout="centered")

st.title("🥗 LeftoversGPT")
st.write(
    "Convert your available pantry ingredients into structured meal plans, nutrition breakdowns, and missing shopping lists using ADK and MCP."
)

user_input = st.text_area(
    "Enter your available ingredients (e.g. chicken, quinoa, spinach):",
    placeholder="chicken, quinoa, spinach, garlic",
)

if st.button("Generate Meal Plan", type="primary"):
    if user_input.strip():
        # Setup layouts for status logs and output blocks
        status_expander = st.expander("⚙️ Execution Log", expanded=True)
        result_box = st.container()

        with status_expander:
            asyncio.run(run_agent(user_input, status_expander, result_box))
    else:
        st.warning("Please enter at least one ingredient.")
