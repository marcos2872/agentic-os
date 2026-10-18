"""Testes do módulo de regras do KWin."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DAEMON_DIR = TESTS_DIR.parent
REPO = DAEMON_DIR.parent
sys.path.insert(0, str(DAEMON_DIR))

from agenticos import kwinrules  # noqa: E402

RULE_ASSET = REPO / "assets/kwin/Transparencia-Global.kwinrule"
RULE_FALLBACK = REPO / "Transparência Global.kwinrule"


def rule_text() -> str:
    source = RULE_ASSET if RULE_ASSET.exists() else RULE_FALLBACK
    return source.read_text(encoding="utf-8")


class KwinRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agenticos-kwin-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.rc = self.tmp / "kwinrulesrc"

    def test_parse_arquivo_de_regra(self) -> None:
        parsed = kwinrules.parse_rule_file(rule_text())
        self.assertEqual(parsed["description"], "Transparência Global")
        self.assertEqual(parsed["fields"]["opacityactive"], "94")
        self.assertEqual(parsed["fields"]["wmclassmatch"], "2")
        self.assertTrue(parsed["id"])

    def test_upsert_cria_atualiza_e_mantem_uma_regra(self) -> None:
        parsed = kwinrules.parse_rule_file(rule_text())
        first = kwinrules.upsert_rule(self.rc, parsed)
        self.assertTrue(first["created"])
        text = self.rc.read_text(encoding="utf-8")
        self.assertIn("Enabled=true", text)
        self.assertIn("count=1", text)

        second = kwinrules.upsert_rule(self.rc, parsed)
        self.assertFalse(second["created"])
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(len(kwinrules.list_rules(self.rc)), 1)

    def test_remove_preserva_campos(self) -> None:
        parsed = kwinrules.parse_rule_file(rule_text())
        applied = kwinrules.upsert_rule(self.rc, parsed)
        removed = kwinrules.remove_rule(self.rc, rule_id=applied["id"], description=parsed["description"])
        self.assertEqual(removed["fields"]["opacityactive"], "94")
        self.assertEqual(kwinrules.list_rules(self.rc), [])
        self.assertIn("count=0", self.rc.read_text(encoding="utf-8"))

    def test_upsert_preserva_enabled_do_arquivo(self) -> None:
        parsed = kwinrules.parse_rule_file(rule_text())
        parsed["fields"]["Enabled"] = "false"
        kwinrules.upsert_rule(self.rc, parsed)
        self.assertFalse(kwinrules.list_rules(self.rc)[0]["enabled"])

        # arquivo sem Enabled (caso do asset embarcado) ativa por padrão
        parsed = kwinrules.parse_rule_file(rule_text())
        parsed["description"] = "Outra regra"
        kwinrules.upsert_rule(self.rc, parsed)
        rules = {rule["description"]: rule["enabled"] for rule in kwinrules.list_rules(self.rc)}
        self.assertTrue(rules["Outra regra"])
        self.assertFalse(rules["Transparência Global"])


if __name__ == "__main__":
    unittest.main()
