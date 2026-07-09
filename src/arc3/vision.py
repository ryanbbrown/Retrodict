"""Optional image-priming: render the opening board and ask a vision model what it sees.

The RGB harness feeds the player model a text grid of integers. A separate vision
model, shown a rendered picture of the same board, tends to read the game's
gestalt — objects, a target, the likely goal — far better than the number grid
reveals. This module renders the board to PNG and returns that model's read, which
the runner injects into the first prompt as a hypothesis for the player to verify.
"""

from __future__ import annotations

import base64
import io
import os

# ARC-AGI-3 16-colour palette (matches the run-inspector viewer).
PALETTE = [
    (255, 255, 255), (204, 204, 204), (153, 153, 153), (102, 102, 102),
    (51, 51, 51), (0, 0, 0), (229, 58, 163), (255, 123, 204),
    (249, 60, 49), (30, 147, 255), (136, 216, 241), (255, 220, 0),
    (255, 133, 27), (146, 18, 49), (79, 204, 48), (163, 86, 214),
]

PROMPT = (
    "this is a game in ARC-AGI-3. what do you see, and what do you think "
    "the goal of the game might be?"
)


def render_board_png(board: list[list[int]], *, cell: int = 12) -> bytes:
    """Render a 2-D grid of colour indices to a nearest-neighbour PNG (the game's own look)."""
    from PIL import Image

    h = len(board)
    w = len(board[0]) if h else 0
    img = Image.new("RGB", (w, h))
    img.putdata([PALETTE[int(c)] for row in board for c in row])
    img = img.resize((w * cell, h * cell), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def describe_opening(board: list[list[int]], *, model: str = "gpt-5.5", api_key: str | None = None) -> tuple[str, bytes]:
    """Render the board and ask an OpenAI vision model to describe it. Returns (description, png_bytes)."""
    from openai import OpenAI

    png = render_board_png(board)
    b64 = base64.b64encode(png).decode()
    client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
    content = [
        {"type": "input_text", "text": PROMPT},
        {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"},
    ]
    resp = client.responses.create(model=model, input=[{"role": "user", "content": content}])  # type: ignore[arg-type]
    return resp.output_text.strip(), png
