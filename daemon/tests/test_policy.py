"""Testes de unidade da política e do contrato tools ↔ ações."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
DAEMON_DIR = TESTS_DIR.parent
REPO = DAEMON_DIR.parent
sys.path.insert(0, str(DAEMON_DIR))

from agenticos import policy  # noqa: E402
from agenticos.actions import REGISTRY, load_all  # noqa: E402


class PolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        load_all()

    def test_riscos_por_acao(self) -> None:
        self.assertEqual(policy.risk_of("flatpak.install"), policy.GREEN)
        self.assertEqual(policy.risk_of("theme.apply_preset"), policy.YELLOW)
        self.assertEqual(policy.risk_of("base.write"), policy.RED)
        self.assertEqual(policy.risk_of("acao.inventada"), policy.RED)

    def test_acao_desconhecida_nao_valida(self) -> None:
        with self.assertRaises(policy.ActionError):
            policy.validate_params("nao.existe", {})

    def test_coercao_tolerante(self) -> None:
        self.assertEqual(policy.validate_params("audit.tail", {"n": "20"})["n"], 20)
        self.assertEqual(policy.validate_params("audit.tail", {"n": 5})["n"], 5)
        params = policy.validate_params("routine.create", {"name": "x", "calendar": "c", "argv": '["notify-send","oi"]'})
        self.assertEqual(params["argv"], ["notify-send", "oi"])

    def test_tipos_estritos(self) -> None:
        with self.assertRaises(policy.ActionError):
            policy.validate_params("config.set", {"file": "a", "group": "g", "key": "k", "value": 1})
        with self.assertRaises(policy.ActionError):
            policy.validate_params("audit.tail", {"n": "vinte"})
        with self.assertRaises(policy.ActionError):
            policy.validate_params("flatpak.install", {"app_id": "x", "extra": "boom"})
        with self.assertRaises(policy.ActionError):
            policy.validate_params("flatpak.install", {})

    def test_toda_acao_tem_handler(self) -> None:
        # `undo.last` é tratada no próprio daemon (precisa do dispatcher).
        self.assertEqual(set(policy.SPEC) - set(REGISTRY), {"undo.last"})
        self.assertTrue(set(REGISTRY) <= set(policy.SPEC))

    def test_tools_doc_inclui_vermelhas(self) -> None:
        doc = {entry["action"]: entry for entry in policy.tools_doc()}
        self.assertEqual(doc["base.write"]["risk"], policy.RED)
        self.assertIn("flatpak.install", doc)

    def test_contrato_com_extensao_do_pi(self) -> None:
        extension = REPO / "pi-package/extensions/agentic-os.ts"
        if not extension.exists():
            self.skipTest("extensão do pi ainda não criada")
        text = extension.read_text(encoding="utf-8")
        pairs = re.findall(r'name:\s*"(os_[a-z0-9_]+)"[\s\S]{0,400}?action:\s*"([a-z0-9_.]+)"', text)
        mapping = dict(pairs)
        self.assertEqual(len(pairs), len(mapping), "tools duplicadas na extensão")
        self.assertEqual(mapping, policy.TOOL_NAMES, "mapeamento tool→ação diverge do daemon")
        for action in policy.TOOL_NAMES.values():
            self.assertIn(action, policy.SPEC)


if __name__ == "__main__":
    unittest.main()
