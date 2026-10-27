"""Tests for the testing-round fixes (Dan's findings): fenced-command parsing and
output truncation (items 1, 5), Ollama per-call caps and streaming (items 2, 4, 6),
the persistent shell with state across commands and timeouts (item 3), and the
reprompt-on-no-command behavior (item 1). Stdlib unittest; the shell tests use a
local bash, not Docker. Run: python -m unittest tests.test_agent_fixes
"""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import Budgets, RunConfig              # noqa: E402
from agent.llm import OllamaBackend                       # noqa: E402
from agent.loop import _parse_action, _truncate_middle, run_agent  # noqa: E402
from agent.llm import MockLLM                             # noqa: E402
from agent.results import OUTCOME_GAVE_UP, OUTCOME_ROOTED  # noqa: E402
from agent.targets import DockerExecTarget, MockTarget    # noqa: E402

BASH = shutil.which("bash")
# the persistent shell runs inside the Linux decoy; skip the local-bash tests off POSIX
HAVE_BASH = os.name == "posix" and BASH is not None


class ParseAndTruncateTests(unittest.TestCase):
    def test_fenced_bash_block(self):
        self.assertEqual(_parse_action("here:\n```bash\nsudo -l\n```"), ("cmd", "sudo -l"))

    def test_fenced_plain_block(self):
        self.assertEqual(_parse_action("```\nid\n```"), ("cmd", "id"))

    def test_cmd_tag_still_wins_over_fence(self):
        self.assertEqual(_parse_action("<cmd>whoami</cmd>\n```\nid\n```"), ("cmd", "whoami"))

    def test_truncate_short_unchanged(self):
        self.assertEqual(_truncate_middle("short", 100), "short")

    def test_truncate_keeps_head_and_tail(self):
        text = "A" * 500 + "B" * 500
        out = _truncate_middle(text, 200)
        self.assertLess(len(out), len(text))
        self.assertIn("truncated", out)
        self.assertTrue(out.startswith("A"))
        self.assertTrue(out.endswith("B"))


class FakeOllamaClient:
    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs = None

    def chat(self, **kwargs):
        self.kwargs = kwargs
        return iter(self.chunks)


class OllamaStreamTests(unittest.TestCase):
    def test_streaming_aggregates_and_caps(self):
        chunks = [
            {"message": {"content": "<cmd>"}},
            {"message": {"content": "id</cmd>"}, "done": True,
             "prompt_eval_count": 12, "eval_count": 3},
        ]
        backend = OllamaBackend("qwen3:8b", num_predict=2048, call_timeout_s=60)
        backend._client = FakeOllamaClient(chunks)
        reply = backend.chat([{"role": "user", "content": "go"}])
        self.assertEqual(reply.content, "<cmd>id</cmd>")
        self.assertEqual(reply.completion_tokens, 3)
        self.assertEqual(reply.prompt_tokens, 12)
        # the per-call token cap is passed through to the model
        self.assertTrue(backend._client.kwargs["stream"])
        self.assertEqual(backend._client.kwargs["options"]["num_predict"], 2048)


@unittest.skipUnless(HAVE_BASH, "bash not available")
class PersistentShellTests(unittest.TestCase):
    def _target(self, **kw):
        t = DockerExecTarget(container="x", exec_argv=[BASH], **kw)
        t.reset()
        return t

    def test_cwd_persists_across_commands(self):
        t = self._target()
        t.run("cd /tmp", 5)
        self.assertIn("/tmp", t.run("pwd", 5).stdout)

    def test_env_persists_across_commands(self):
        t = self._target()
        t.run("export FOO=bar", 5)
        self.assertIn("bar", t.run("echo $FOO", 5).stdout)

    def test_exit_codes(self):
        t = self._target()
        self.assertEqual(t.run("true", 5).exit_code, 0)
        self.assertNotEqual(t.run("false", 5).exit_code, 0)

    def test_command_timeout(self):
        t = self._target()
        out = t.run("sleep 3", 0.3)
        self.assertIsNone(out.exit_code)
        self.assertIn("timeout", out.stderr)

    def test_is_rooted_check(self):
        self.assertTrue(self._target(root_check_cmd="echo 0", root_check_expect="0").is_rooted())
        self.assertFalse(self._target(root_check_cmd="echo 1", root_check_expect="0").is_rooted())


class RepromptTests(unittest.TestCase):
    def _cfg(self, **kw):
        kw.setdefault("budgets", Budgets(max_steps=10, wall_clock_cap_s=30))
        return RunConfig(target_kind="mock", results_dir=tempfile.mkdtemp(), **kw)

    def test_reprompt_then_recovers(self):
        replies = iter(["I should probably look around first.",
                        "<cmd>sudo cat /root/flag</cmd>"])
        target = MockTarget(script={"sudo cat /root/flag": "FLAG{x}"})
        res = run_agent(self._cfg(), llm=MockLLM(lambda _m: next(replies, "<done>x</done>")),
                        target=target)
        self.assertTrue(res.success)
        self.assertEqual(res.outcome, OUTCOME_ROOTED)

    def test_gives_up_after_reprompts(self):
        res = run_agent(self._cfg(budgets=Budgets(max_steps=10, max_no_cmd_retries=2,
                                                  wall_clock_cap_s=30)),
                        llm=MockLLM(lambda _m: "I am not sure what to do here."),
                        target=MockTarget())
        self.assertEqual(res.outcome, OUTCOME_GAVE_UP)
        lines = Path(res.transcript_path).read_text().splitlines()
        self.assertTrue(any("reprompt" in ln for ln in lines))
        self.assertEqual(res.steps_taken, 3)  # 2 reprompts + final give-up


if __name__ == "__main__":
    unittest.main(verbosity=2)
