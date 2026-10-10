import json
import tempfile
import unittest
from pathlib import Path

from vertex_agent.config import assert_workspace_allowed
from vertex_agent.memory import MemoryStore
from vertex_agent.tools import Toolbox, matlab_entry_name, matlab_is_function


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project = root / "proj"
        self.workspace = root / "work"
        package = self.project / "vertex_agent"
        package.mkdir(parents=True)
        (package / "sample.py").write_bytes(b"VALUE = 1\n")
        (package / "prompts.py").write_bytes(b"TEXT = 'old'\n")
        self.data = root / "data"
        self.box = Toolbox(self.project, self.workspace, self.data, MemoryStore(self.data / "memory.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, **kwargs):
        return json.loads(self.box.execute("apply_edit", kwargs))

    def test_replace_and_run_python(self):
        target = self.workspace / "add.py"
        target.write_text("print(1 + 2)\n", encoding="utf-8")
        result = self.edit(
            scope="workspace",
            path="add.py",
            kind="replace",
            old_string="1 + 2",
            new_string="4 + 5",
            reason="修改求和",
        )
        self.assertTrue(result["ok"])
        self.assertIn("+", result["diff"])
        ran = json.loads(self.box.execute("run_code", {"language": "python", "path": "add.py"}))
        self.assertEqual(ran["returncode"], 0)
        self.assertIn("9", ran["stdout"])

    def test_crlf_is_preserved(self):
        (self.workspace / "win.py").write_bytes(b"A = 1\r\nB = 2\r\n")
        result = self.edit(
            scope="workspace",
            path="win.py",
            kind="replace",
            old_string="A = 1\n",
            new_string="A = 3\n",
            reason="换行",
        )
        self.assertTrue(result["ok"])
        data = (self.workspace / "win.py").read_bytes()
        self.assertIn(b"A = 3\r\n", data)
        self.assertIn(b"B = 2\r\n", data)

    def test_ambiguous_and_escape_and_secret(self):
        (self.workspace / "dup.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
        ambiguous = self.edit(scope="workspace", path="dup.py", kind="replace", old_string="x = 1", new_string="x = 2", reason="重复")
        self.assertFalse(ambiguous["ok"])
        escaped = self.edit(scope="workspace", path="../proj/vertex_agent/sample.py", kind="replace", old_string="VALUE = 1", new_string="VALUE = 2", reason="越界")
        self.assertFalse(escaped["ok"])
        secret = self.edit(scope="workspace", path=".env", kind="write", content="KEY=1\n", reason="密钥")
        self.assertFalse(secret["ok"])

    def test_agent_syntax_rolls_back(self):
        result = self.edit(
            scope="agent",
            path="vertex_agent/sample.py",
            kind="replace",
            old_string="VALUE = 1\n",
            new_string="VALUE =\n",
            reason="故意写坏",
        )
        self.assertFalse(result["ok"])
        self.assertIn("已回滚", result["error"])
        self.assertEqual((self.project / "vertex_agent" / "sample.py").read_bytes(), b"VALUE = 1\n")

    def test_agent_edit_restart_flag_and_rollback(self):
        changed = self.edit(
            scope="agent",
            path="vertex_agent/sample.py",
            kind="lines",
            start_line=1,
            end_line=1,
            content="VALUE = 2",
            reason="调整常量",
        )
        self.assertTrue(changed["ok"])
        self.assertTrue(changed["restart_required"])
        prompt = self.edit(
            scope="agent",
            path="vertex_agent/prompts.py",
            kind="replace",
            old_string="old",
            new_string="new",
            reason="改提示词",
        )
        self.assertTrue(prompt["ok"])
        self.assertFalse(prompt["restart_required"])
        restored = self.box.rollback(changed["edit_id"])
        self.assertTrue(restored["ok"])
        self.assertIn(b"VALUE = 1", (self.project / "vertex_agent" / "sample.py").read_bytes())

    def test_write_refuses_to_overwrite(self):
        (self.workspace / "keep.py").write_text("print(1)\n", encoding="utf-8")
        result = self.edit(scope="workspace", path="keep.py", kind="write", content="print(2)\n", reason="覆盖")
        self.assertFalse(result["ok"])
        self.assertEqual((self.workspace / "keep.py").read_text(encoding="utf-8"), "print(1)\n")

    def test_new_file_rollback_deletes_it(self):
        created = self.edit(scope="workspace", path="fresh.py", kind="write", content="print('hi')\n", reason="新建")
        self.assertTrue(created["ok"])
        self.assertTrue((self.workspace / "fresh.py").exists())
        self.box.rollback(created["edit_id"])
        self.assertFalse((self.workspace / "fresh.py").exists())

    def test_self_edit_can_be_disabled(self):
        self.box.self_edit = False
        result = self.edit(scope="agent", path="vertex_agent/sample.py", kind="replace", old_string="VALUE = 1", new_string="VALUE = 9", reason="关闭")
        self.assertFalse(result["ok"])

    def test_memory_and_validate(self):
        remembered = json.loads(self.box.execute("remember", {"text": "注释使用中文"}))
        self.assertTrue(remembered["ok"])
        found = json.loads(self.box.execute("recall", {"query": "中文"}))
        self.assertEqual(found["notes"][0]["text"], "注释使用中文")
        report = json.loads(self.box.execute("validate_agent", {}))
        self.assertTrue(report["ok"])

    def test_matlab_function_entry(self):
        function_file = "function [a, b] = sound_sensor_sim(x)\na = x;\nend\n"
        self.assertTrue(matlab_is_function(function_file))
        self.assertEqual(matlab_entry_name(function_file), "sound_sensor_sim")
        script = "% note\nfprintf('ok\\n');\n"
        self.assertFalse(matlab_is_function(script))
        self.assertIsNone(matlab_entry_name(script))
        self.assertEqual(matlab_entry_name("function y = add_one(x)\ny = x + 1;\nend\n"), "add_one")

    def test_verify_python_pass_and_fail(self):
        (self.workspace / "check_ok.py").write_text("print('PASS')\n", encoding="utf-8")
        passed = json.loads(self.box.build_action("workspace", "check_ok.py", "verify"))
        self.assertTrue(passed["ok"])
        self.assertEqual(passed["diagnosis"], "自我验证通过")
        self.assertIn("PASS", passed["stdout"])
        (self.workspace / "check_bad.py").write_text("raise SystemExit('boom')\n", encoding="utf-8")
        failed = json.loads(self.box.build_action("workspace", "check_bad.py", "verify"))
        self.assertFalse(failed["ok"])
        self.assertIn("未通过", failed["diagnosis"])

    def test_workspace_cannot_cover_agent_tree(self):
        with self.assertRaises(ValueError):
            assert_workspace_allowed(self.project, self.project)
        with self.assertRaises(ValueError):
            assert_workspace_allowed(self.project.parent, self.project)


if __name__ == "__main__":
    unittest.main()
