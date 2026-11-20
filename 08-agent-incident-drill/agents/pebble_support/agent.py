"""The Pebble Post customer-service agent (Google ADK). ADK loads `root_agent` from here."""

from config import (
    MAX_REFUND_MINOR,
    MODEL_ATTEMPTS,
    MODEL_ID,
    MODEL_MAX_DELAY_S,
    MODEL_TIMEOUT_MS,
)
from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai import types

from .tools import lookup_order, refund_order

INSTRUCTION = f"""You are the customer-service agent for Pebble Post, a parcel shop.
Look up the order before you promise anything. Use only the tools for facts about orders.
To refund, call refund_order with the order currency from lookup_order.
Refunds are capped at {MAX_REFUND_MINOR} minor units. If a tool refuses, say so plainly
and offer to pass the customer to a human. Never claim a refund happened unless the tool said so."""

# Model calls: 30 s per attempt, at most 2 attempts on transient HTTP errors (429, 5xx).
# Only the model request is retried. Tools run once per tool call, so a retry never
# replays a refund. Worst case for a whole request is 4 calls * (2 * 30 s + 4 s) = 256 s, under the 300 s
# Cloud Run timeout (see config.py).
MODEL = Gemini(
    model=MODEL_ID,
    retry_options=types.HttpRetryOptions(attempts=MODEL_ATTEMPTS, initial_delay=1, max_delay=MODEL_MAX_DELAY_S),
)

root_agent = Agent(
    name="pebble_support",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=MODEL_TIMEOUT_MS),
    ),
    description="Answers Pebble Post order questions and issues small refunds.",
    instruction=INSTRUCTION,
    tools=[lookup_order, refund_order],
)
