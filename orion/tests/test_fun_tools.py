from tools.fun_tools import CoinFlipTool, MagicEightBallTool, RandomQuoteTool, RollDiceTool


def test_coin_flip_is_heads_or_tails():
    assert CoinFlipTool().run() in {"Heads", "Tails"}


def test_roll_dice_default():
    result = RollDiceTool().run()
    assert result.startswith("Rolled 1d6:")


def test_roll_dice_notation_and_bounds():
    result = RollDiceTool().run(notation="2d6")
    assert "Rolled 2d6:" in result


def test_roll_dice_rejects_absurd_input():
    import pytest

    with pytest.raises(ValueError):
        RollDiceTool().run(notation="1000d1000")


def test_magic_eight_ball_returns_nonempty_answer():
    assert len(MagicEightBallTool().run(question="Will it rain?")) > 0


def test_random_quote_has_attribution():
    assert "—" in RandomQuoteTool().run()
