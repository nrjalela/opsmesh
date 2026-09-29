"""One tiny API call to confirm the configured model ID works before spending on a batch."""

import sys

import anthropic

from opsmesh.agents.llm import api_key_available, client, model_name

if not api_key_available():
    sys.exit("ANTHROPIC_API_KEY is not set in .env")

model = model_name()
try:
    resp = client().messages.create(
        model=model,
        max_tokens=64,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
except anthropic.NotFoundError:
    sys.exit(f"Model '{model}' was not found. Check OPSMESH_MODEL.")
except anthropic.AuthenticationError:
    sys.exit("The API key was rejected.")

text = "".join(b.text for b in resp.content if b.type == "text").strip()
print(f"model={resp.model} stop_reason={resp.stop_reason} reply={text!r} "
      f"tokens={resp.usage.input_tokens}in/{resp.usage.output_tokens}out")
