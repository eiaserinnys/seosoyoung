"""Tests for core/context.py — hook context factory."""

from seosoyoung.core.context import create_hook_context


class TestCreateHookContext:
    def test_creates_with_name_and_kwargs(self):
        ctx = create_hook_context("on_message", text="hello", user="U123")
        assert ctx.hook_name == "on_message"
        assert ctx.args == {"text": "hello", "user": "U123"}
        assert ctx.results == []
        assert ctx.stopped is False

    def test_creates_with_no_kwargs(self):
        ctx = create_hook_context("empty")
        assert ctx.hook_name == "empty"
        assert ctx.args == {}

    def test_independent_instances(self):
        ctx1 = create_hook_context("a", x=1)
        ctx2 = create_hook_context("b", y=2)
        ctx1.results.append("val")
        assert ctx2.results == []
        assert ctx1.args != ctx2.args
