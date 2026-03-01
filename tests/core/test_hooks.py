"""Tests for core/hooks.py — HookPriority, HookResult, HookContext."""

from seosoyoung.core.hooks import HookContext, HookPriority, HookResult


class TestHookPriority:
    def test_ordering(self):
        assert HookPriority.CRITICAL > HookPriority.HIGH
        assert HookPriority.HIGH > HookPriority.NORMAL
        assert HookPriority.NORMAL > HookPriority.LOW

    def test_int_values(self):
        assert int(HookPriority.LOW) == 0
        assert int(HookPriority.NORMAL) == 50
        assert int(HookPriority.HIGH) == 100
        assert int(HookPriority.CRITICAL) == 200

    def test_sortable(self):
        priorities = [
            HookPriority.NORMAL,
            HookPriority.CRITICAL,
            HookPriority.LOW,
            HookPriority.HIGH,
        ]
        assert sorted(priorities, reverse=True) == [
            HookPriority.CRITICAL,
            HookPriority.HIGH,
            HookPriority.NORMAL,
            HookPriority.LOW,
        ]

    def test_comparable_with_int(self):
        assert HookPriority.NORMAL == 50
        assert HookPriority.HIGH > 99


class TestHookResult:
    def test_values(self):
        assert HookResult.CONTINUE.value == "continue"
        assert HookResult.STOP.value == "stop"
        assert HookResult.SKIP.value == "skip"

    def test_members(self):
        assert set(HookResult.__members__) == {"CONTINUE", "STOP", "SKIP"}


class TestHookContext:
    def test_defaults(self):
        ctx = HookContext(hook_name="test")
        assert ctx.hook_name == "test"
        assert ctx.args == {}
        assert ctx.results == []
        assert ctx.stopped is False

    def test_with_args(self):
        ctx = HookContext(hook_name="on_message", args={"text": "hello"})
        assert ctx.args["text"] == "hello"

    def test_mutable_results(self):
        ctx = HookContext(hook_name="test")
        ctx.results.append("value1")
        ctx.results.append("value2")
        assert ctx.results == ["value1", "value2"]

    def test_stopped_flag(self):
        ctx = HookContext(hook_name="test")
        assert not ctx.stopped
        ctx.stopped = True
        assert ctx.stopped

    def test_independent_instances(self):
        ctx1 = HookContext(hook_name="a")
        ctx2 = HookContext(hook_name="b")
        ctx1.results.append("x")
        assert ctx2.results == []
