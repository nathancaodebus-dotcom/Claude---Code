"""Purely-for-fun tools — no productivity justification needed, a second
self should also be able to just mess around."""
from __future__ import annotations

import random

import httpx

from core.http import client
from tools.base import Tool

_EIGHT_BALL_ANSWERS = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
    "As I see it, yes.", "Most likely.", "Outlook good.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.",
    "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful.",
]

_QUOTES = [
    ("The only way to do great work is to love what you do.", "Steve Jobs"),
    ("Sometimes you gotta run before you can walk.", "Tony Stark"),
    ("I am Iron Man.", "Tony Stark"),
    ("Genius, billionaire, playboy, philanthropist.", "Tony Stark"),
    ("Part of the journey is the end.", "Tony Stark"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
]


class CoinFlipTool(Tool):
    name = "flip_coin"
    description = "Flip a coin."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        return random.choice(["Heads", "Tails"])


class RollDiceTool(Tool):
    name = "roll_dice"
    description = "Roll dice using standard notation, e.g. '2d6' (two six-sided dice) or 'd20'."
    input_schema = {
        "type": "object",
        "properties": {"notation": {"type": "string", "description": "Default '1d6'."}},
    }

    def run(self, notation: str = "1d6") -> str:
        notation = notation.lower().replace(" ", "")
        count_str, sides_str = notation.split("d") if "d" in notation else ("1", notation)
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
        if not (1 <= count <= 100 and 2 <= sides <= 1000):
            raise ValueError("Keep it reasonable: 1-100 dice, 2-1000 sides.")
        rolls = [random.randint(1, sides) for _ in range(count)]
        return f"Rolled {notation}: {rolls} = {sum(rolls)}"


class MagicEightBallTool(Tool):
    name = "magic_eight_ball"
    description = "Ask the magic 8-ball a yes/no question and get a classic cryptic answer."
    input_schema = {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    }

    def run(self, question: str) -> str:
        return random.choice(_EIGHT_BALL_ANSWERS)


class RandomQuoteTool(Tool):
    name = "random_quote"
    description = "Get a random inspirational (or Tony Stark) quote."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        text, author = random.choice(_QUOTES)
        return f'"{text}" — {author}'


class JokeTool(Tool):
    name = "tell_joke"
    description = "Tell a random joke."
    input_schema = {"type": "object", "properties": {}}

    def run(self) -> str:
        try:
            response = client.get("https://official-joke-api.appspot.com/random_joke", timeout=10)
            response.raise_for_status()
            data = response.json()
            return f"{data['setup']} ... {data['punchline']}"
        except httpx.HTTPError:
            return "Why do programmers prefer dark mode? Because light attracts bugs."
