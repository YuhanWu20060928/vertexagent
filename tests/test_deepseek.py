import json
import tempfile
import unittest
from pathlib import Path

from vertex_agent.agent import matlab_code_only
from vertex_agent.config import MATLAB_LOCAL_MODEL, model_base, model_for_task, resolve_chat_model
from vertex_agent.deepseek import adapt_messages
from vertex_agent.secrets import api_model_id, is_deepseek_model, is_loopback, key_status, mask_key, save_api_key


class DeepSeekLocalKeyTests(unittest.TestCase):
    def test_mask_and_status_hide_the_key(self):
        secret = "sk-testsecretvalue123456"
        self.assertTrue(mask_key(secret).startswith("sk-tes"))
        self.assertNotIn("secretvalue", mask_key(secret))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_api_key(root, secret)
            status = key_status(root)
            self.assertTrue(status["registered"])
            self.assertNotIn(secret, json.dumps(status))
            self.assertEqual(status["model"], "deepseek-flash")

    def test_loopback_and_model_name(self):
        self.assertTrue(is_loopback("127.0.0.1"))
        self.assertTrue(is_loopback("::1"))
        self.assertFalse(is_loopback("10.7.197.249"))
        self.assertTrue(is_deepseek_model("deepseek-flash"))
        self.assertTrue(is_deepseek_model("deepseek-v4.1-flash"))
        self.assertTrue(is_deepseek_model("deepseek-v4-pro"))
        self.assertEqual(api_model_id("deepseek-v4.1-pro"), "deepseek-v4-pro")
        self.assertEqual(api_model_id("deepseek-flash"), "deepseek-flash")
        self.assertFalse(is_deepseek_model("qwen2.5:7b"))
        self.assertFalse(is_deepseek_model("deepseek-r1:8b"))
        self.assertFalse(is_deepseek_model(MATLAB_LOCAL_MODEL))
        self.assertEqual(model_base("matlab-r2024b:latest"), MATLAB_LOCAL_MODEL)
        self.assertEqual(model_base("Qwen3.5:4b"), "qwen3.5:4b")

    def test_chat_uses_the_model_the_user_selected(self):
        self.assertEqual(resolve_chat_model("deepseek-flash", "qwen2.5:7b"), "qwen2.5:7b")
        self.assertEqual(resolve_chat_model("deepseek-flash", "  matlab-r2024b  "), MATLAB_LOCAL_MODEL)
        self.assertEqual(resolve_chat_model("qwen2.5:7b", None), "qwen2.5:7b")
        self.assertEqual(resolve_chat_model("qwen2.5:7b", ""), "qwen2.5:7b")
        with self.assertRaises(ValueError):
            resolve_chat_model("", None)
        with self.assertRaises(ValueError):
            resolve_chat_model("qwen2.5:7b", "bad/name")

    def test_code_languages_are_python_c_cpp(self):
        self.assertEqual(
            model_for_task("qwen3.5:4b", "qwen3.5:4b", language="python", mode="workspace"),
            "qwen3.5:4b",
        )
        self.assertEqual(
            model_for_task("qwen3.5:4b", "deepseek-flash", language="cpp", mode="workspace"),
            "deepseek-flash",
        )
        self.assertEqual(
            model_for_task("qwen3.5:4b", "deepseek-v4-pro", language="python", mode="workspace"),
            "deepseek-v4-pro",
        )
        with self.assertRaises(ValueError):
            model_for_task("qwen3.5:4b", "deepseek-r1:8b", language="cpp", mode="workspace")
        with self.assertRaises(ValueError):
            model_for_task("qwen2.5:7b", "qwen2.5:7b", language="matlab", mode="workspace")
        with self.assertRaises(ValueError):
            model_for_task("qwen2.5:7b", "qwen2.5:7b", language="solidworks", mode="workspace")

    def test_matlab_reply_is_code_only(self):
        raw = "你的代码在工作区里，共 3 行，内容如下：\n```matlab\nx = 1;\ndisp(x)\n```\n已跑通。"
        self.assertEqual(matlab_code_only(raw), "```matlab\nx = 1;\ndisp(x)\n```")
        self.assertEqual(matlab_code_only("```matlab\nA = eye(2);\n```"), "```matlab\nA = eye(2);\n```")
        tool = '好的，请调用 apply_edit。\n{"name":"apply_edit","arguments":{"path":"a.m","kind":"write","content":"x = 1;\\ndisp(x)\\n"}}\n请运行上述代码以保存文件。'
        self.assertEqual(matlab_code_only(tool), "```matlab\nx = 1;\ndisp(x)\n```")

    def test_tool_history_keeps_reasoning_and_stringifies_arguments(self):
        messages = adapt_messages(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "先读文件",
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "read_file", "arguments": {"path": "hello.py"}}}
                    ],
                }
            ]
        )
        self.assertEqual(messages[0]["reasoning_content"], "先读文件")
        self.assertEqual(messages[0]["tool_calls"][0]["function"]["arguments"], '{"path": "hello.py"}')


if __name__ == "__main__":
    unittest.main()
