import io
import json
import unittest
from contextlib import redirect_stdout

from kbprep_worker.envelope import EnvelopeExit
from kbprep_worker.typing_helpers import as_int, as_list, as_object, as_path_string, as_str, require_object


class TypingHelperTests(unittest.TestCase):
    def test_as_object_and_as_list_return_empty_defaults_for_wrong_shapes(self):
        self.assertEqual(as_object({"ok": True}), {"ok": True})
        self.assertEqual(as_object(None), {})
        self.assertEqual(as_object(["bad"]), {})
        self.assertEqual(as_list(["a", 1]), ["a", 1])
        self.assertEqual(as_list({"bad": True}), [])

    def test_as_str_as_int_and_as_path_string_are_deterministic(self):
        self.assertEqual(as_str(" value "), " value ")
        self.assertIsNone(as_str(42))
        self.assertEqual(as_int("12", default=3), 12)
        self.assertEqual(as_int(7, default=3), 7)
        self.assertEqual(as_int("bad", default=3), 3)
        self.assertEqual(as_path_string(" C:/tmp/file.md "), "C:/tmp/file.md")
        self.assertIsNone(as_path_string(""))
        self.assertIsNone(as_path_string(None))

    def test_require_object_fails_with_structured_error_for_wrong_shape(self):
        stdout = io.StringIO()
        with self.assertRaises(EnvelopeExit) as raised:
            with redirect_stdout(stdout):
                require_object([], field_name="proposal", code="E_INVALID_INPUT")

        self.assertEqual(raised.exception.code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "E_INVALID_INPUT")
        self.assertEqual(payload["error"]["details"]["field"], "proposal")


if __name__ == "__main__":
    unittest.main()
