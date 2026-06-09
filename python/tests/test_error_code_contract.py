import re
import unittest
from pathlib import Path

from kbprep_worker.error_codes import KBPREP_ERROR_CODES, KBPREP_WARNING_CODES


ROOT = Path(__file__).resolve().parents[2]


class ErrorCodeContractTests(unittest.TestCase):
    def test_typescript_and_python_error_code_lists_match(self):
        ts_source = (ROOT / "src/errorCodes.ts").read_text(encoding="utf-8")
        ts_errors = set(re.findall(r'"(E_[A-Z0-9_]+|KBPREP_[A-Z0-9_]+)"', ts_source))
        ts_warnings = set(re.findall(r'"(W_[A-Z0-9_]+)"', ts_source))

        self.assertEqual(ts_errors - {code for code in ts_errors if code.startswith("KBPREP_")}, KBPREP_ERROR_CODES)
        self.assertEqual(ts_warnings, KBPREP_WARNING_CODES)

    def test_source_does_not_introduce_unregistered_codes(self):
        registered = KBPREP_ERROR_CODES | KBPREP_WARNING_CODES | {
            "KBPREP_INVALID_INPUT",
            "KBPREP_WORKER_TIMEOUT",
            "KBPREP_WORKER_BAD_JSON",
            "KBPREP_CANCELLED",
            "KBPREP_INTERNAL",
        }
        offenders: list[str] = []
        for folder in [ROOT / "src", ROOT / "python/kbprep_worker"]:
            for path in folder.rglob("*"):
                if path.suffix not in {".ts", ".py"} or "__pycache__" in path.parts or path.name.endswith(".test.ts"):
                    continue
                text = path.read_text(encoding="utf-8")
                for code in re.findall(r'"([EW]_[A-Z0-9_]+)"|\'([EW]_[A-Z0-9_]+)\'', text):
                    value = code[0] or code[1]
                    if value.endswith("_"):
                        continue
                    if value not in registered:
                        offenders.append(f"{path.relative_to(ROOT)}:{value}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
