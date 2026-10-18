"""Testes de integração: daemon real + CLI, com ferramentas stubbadas."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

import support  # noqa: E402


class E2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agenticos-e2e-"))
        self.h = support.Harness(self.tmp)

        def cleanup() -> None:
            self.h.stop()
            shutil.rmtree(self.tmp, ignore_errors=True)

        self.addCleanup(cleanup)

    # ------------------------------------------------------------- básicos
    def test_ping_e_tools(self) -> None:
        pong = self.h.call("ping")
        self.assertTrue(pong["ok"])
        self.assertTrue(pong["result"]["pong"])

        tools = self.h.call("tools")
        self.assertTrue(tools["ok"])
        self.assertGreater(tools["result"]["count"], 20)

    def test_acoes_vermelhas_e_desconhecidas_bloqueadas(self) -> None:
        blocked = self.h.call("base.write")
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["risk"], "red")
        self.assertIn("bloqueada", blocked["error"])

        unknown = self.h.call("frobnicate")
        self.assertFalse(unknown["ok"])
        self.assertIn("desconhecida", unknown["error"])

    def test_segundo_daemon_e_recusado(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "agenticos.daemon", "--socket", str(self.h.socket)],
            env=self.h.env,
            cwd=str(support.DAEMON_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("já existe", proc.stderr)

    def test_cli_subprocess(self) -> None:
        code, payload = self.h.cli("tools")
        self.assertEqual(code, 0)
        self.assertTrue(payload and payload["ok"])
        self.assertGreater(payload["result"]["count"], 20)

    # ------------------------------------------------------------- config
    def test_config_roundtrip_com_undo(self) -> None:
        first = self.h.call("config.set", {"file": "teste.ini", "group": "G", "key": "K", "value": "1"})
        self.assertTrue(first["ok"])
        self.assertTrue(first["undo_id"])

        got = self.h.call("config.get", {"file": "teste.ini", "group": "G", "key": "K"})
        self.assertEqual(got["result"]["value"], "1")

        self.h.call("config.set", {"file": "teste.ini", "group": "G", "key": "K", "value": "2"})
        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        self.assertFalse(undone["result"]["errors"])

        got = self.h.call("config.get", {"file": "teste.ini", "group": "G", "key": "K"})
        self.assertEqual(got["result"]["value"], "1")

    def test_config_protege_caminhos(self) -> None:
        escape = self.h.call("config.set", {"file": "../fora.ini", "group": "G", "key": "K", "value": "x"})
        self.assertFalse(escape["ok"])
        absolute = self.h.call("config.set", {"file": "/etc/kdeglobals", "group": "G", "key": "K", "value": "x"})
        self.assertFalse(absolute["ok"])

    # --------------------------------------------------------------- tema
    def test_theme_preset_fluxo_amarelo(self) -> None:
        plan = self.h.call("theme.apply_preset")
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["needs_confirmation"])
        self.assertEqual(plan["risk"], "yellow")
        self.assertIn("plan_id", plan)

        bad = self.h.call("theme.apply_preset", confirm="inexistente")
        self.assertFalse(bad["ok"])
        self.assertIn("expirado", bad["error"])

        applied = self.h.call("theme.apply_preset", confirm=plan["plan_id"])
        self.assertTrue(applied["ok"], applied)
        rc = (self.h.home / ".config/kwinrulesrc").read_text(encoding="utf-8")
        self.assertIn("Transparência Global", rc)
        self.assertIn("opacityactive=94", rc)
        self.assertIn("Enabled=true", rc)
        kdeglobals = (self.h.home / ".config/kdeglobals").read_text(encoding="utf-8")
        self.assertIn("ColorScheme=BreezeDark", kdeglobals)

        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        rules = self.h.call("kwin.list_rules")
        self.assertEqual(rules["result"]["count"], 0)

    def test_kwin_regra_idempotente_e_remocao(self) -> None:
        rule_file = str(self.h.home / ".local/share/agenticos/assets/Transparencia-Global.kwinrule")
        first = self.h.call("kwin.add_rule", {"file": rule_file}, yes=True)
        self.assertTrue(first["ok"])
        second = self.h.call("kwin.add_rule", {"file": rule_file}, yes=True)
        self.assertFalse(second["result"]["created"])
        self.assertEqual(self.h.call("kwin.list_rules")["result"]["count"], 1)

        removed = self.h.call("kwin.remove_rule", {"description": "Transparência Global"}, yes=True)
        self.assertTrue(removed["ok"])
        self.assertEqual(self.h.call("kwin.list_rules")["result"]["count"], 0)

    # ------------------------------------------------------------- flatpak
    def test_flatpak_install_desinstall_com_undo(self) -> None:
        installed = self.h.call("flatpak.install", {"app_id": "com.example.App"})
        self.assertTrue(installed["ok"], installed)
        self.assertIn("flatpak install", self.h.stub_calls())

        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        self.assertIn("flatpak uninstall", self.h.stub_calls())

    def test_flatpak_scope_system_escala_para_amarelo(self) -> None:
        escalated = self.h.call("flatpak.install", {"app_id": "com.example.App", "scope": "system"})
        self.assertTrue(escalated["ok"])
        self.assertTrue(escalated["needs_confirmation"])
        self.assertEqual(escalated["risk"], "yellow")

        confirmed = self.h.call(
            "flatpak.install", {"app_id": "com.example.App", "scope": "system"}, confirm=escalated["plan_id"]
        )
        self.assertTrue(confirmed["ok"], confirmed)
        self.assertIn("--system", self.h.stub_calls())

    def test_flatpak_app_id_invalido(self) -> None:
        bad = self.h.call("flatpak.install", {"app_id": "; rm -rf /"})
        self.assertFalse(bad["ok"])

    # ------------------------------------------------------------- rotinas
    def test_rotina_ciclo_completo(self) -> None:
        created = self.h.call(
            "routine.create",
            {"name": "backup", "calendar": "Sun *-*-* 10:00", "argv": ["notify-send", "backup ok"]},
        )
        self.assertTrue(created["ok"], created)
        unit_dir = self.h.home / ".config/systemd/user"
        self.assertTrue((unit_dir / "agenticos-backup.timer").exists())
        self.assertTrue((unit_dir / "agenticos-backup.service").exists())
        self.assertIn("systemctl --user enable --now agenticos-backup.timer", self.h.stub_calls())

        listed = self.h.call("routine.list")
        names = [item["name"] for item in listed["result"]["routines"]]
        self.assertIn("backup", names)
        self.assertEqual(listed["result"]["routines"][0]["calendar"], "Sun *-*-* 10:00")

        ran = self.h.call("routine.run", {"name": "backup"})
        self.assertTrue(ran["ok"])

        removed = self.h.call("routine.remove", {"name": "backup"})
        self.assertTrue(removed["ok"])
        self.assertFalse((unit_dir / "agenticos-backup.timer").exists())

        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        self.assertTrue((unit_dir / "agenticos-backup.timer").exists())

    def test_rotina_comando_nao_permitido(self) -> None:
        bad = self.h.call(
            "routine.create", {"name": "hack", "calendar": "daily", "argv": ["bash", "-c", "rm -rf /"]}
        )
        self.assertFalse(bad["ok"])
        self.assertIn("não permitido", bad["error"])

    def test_rotina_calendario_invalido(self) -> None:
        bad = self.h.call("routine.create", {"name": "x", "calendar": "", "argv": ["notify-send", "oi"]})
        self.assertFalse(bad["ok"])

    # ------------------------------------------------------------- widgets
    def test_widget_ciclo_completo(self) -> None:
        source = self.h.make_widget()
        installed = self.h.call("widget.install", {"path": str(source)})
        self.assertTrue(installed["ok"], installed)
        self.assertEqual(installed["result"]["installed"], "com.agenticos.testwidget")

        listed = self.h.call("widget.list")
        self.assertIn("com.agenticos.testwidget", [item["id"] for item in listed["result"]["widgets"]])

        removed = self.h.call("widget.remove", {"id": "com.agenticos.testwidget"})
        self.assertTrue(removed["ok"])
        self.assertEqual(self.h.call("widget.list")["result"]["count"], 0)

        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        self.assertIn("com.agenticos.testwidget", [item["id"] for item in self.h.call("widget.list")["result"]["widgets"]])

    def test_widget_instalacao_fora_do_home(self) -> None:
        bad = self.h.call("widget.install", {"path": "/usr/share/plasma/plasmoids/x"})
        self.assertFalse(bad["ok"])

    # ---------------------------------------------------------------- fs
    def test_fs_read_permite_e_bloqueia(self) -> None:
        allowed = self.h.call("fs.read", {"path": "/etc/hostname"})
        self.assertTrue(allowed["ok"], allowed)

        secret = self.h.home / ".ssh"
        secret.mkdir(exist_ok=True)
        (secret / "id_rsa").write_text("chave", encoding="utf-8")
        blocked = self.h.call("fs.read", {"path": str(secret / "id_rsa")})
        self.assertFalse(blocked["ok"])
        self.assertIn("bloqueado", blocked["error"])

        outside = self.h.call("fs.read", {"path": "/usr/lib/os-release"})
        self.assertFalse(outside["ok"])

    # ------------------------------------------------------------ serviços
    def test_service_user_operacoes(self) -> None:
        status = self.h.call("service.user", {"unit": "agenticd.service", "op": "status"})
        self.assertTrue(status["ok"], status)
        self.assertEqual(status["result"]["active"], "active")

        enable = self.h.call("service.user", {"unit": "teste.timer", "op": "enable"})
        self.assertTrue(enable["ok"])
        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        self.assertIn("systemctl --user disable teste.timer", self.h.stub_calls())

        bad_unit = self.h.call("service.user", {"unit": "../../etc/passwd", "op": "start"})
        self.assertFalse(bad_unit["ok"])

    # ------------------------------------------------------------- auditoria
    def test_auditoria_registra_acoes(self) -> None:
        self.h.call("config.set", {"file": "a.ini", "group": "G", "key": "K", "value": "v"})
        self.h.call("base.write")
        tail = self.h.call("audit.tail", {"n": 10})
        actions = [entry["action"] for entry in tail["result"]["entries"]]
        self.assertIn("config.set", actions)
        self.assertIn("base.write", actions)
        blocked = [entry for entry in tail["result"]["entries"] if entry["action"] == "base.write"]
        self.assertFalse(blocked[-1]["ok"])

    def test_undo_sem_entradas(self) -> None:
        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"])
        self.assertIsNone(undone["result"]["undone"])

    # ------------------------------------------- correções da revisão (v1)
    def test_fs_read_bloqueia_fstab_e_ssh_host_key(self) -> None:
        for path in ("/etc/fstab", "/etc/ssh/ssh_host_rsa_key"):
            blocked = self.h.call("fs.read", {"path": path})
            self.assertFalse(blocked["ok"], path)
            self.assertIn("bloqueado", blocked["error"])

    def test_config_rejeita_injecao(self) -> None:
        newline = self.h.call(
            "config.set", {"file": "x.ini", "group": "G", "key": "K", "value": "a\n[secao]"}
        )
        self.assertFalse(newline["ok"])
        bad_group = self.h.call(
            "config.set", {"file": "x.ini", "group": "G]\n[outra", "key": "K", "value": "v"}
        )
        self.assertFalse(bad_group["ok"])

    def test_config_unset_direto_e_undo(self) -> None:
        self.h.call("config.set", {"file": "u.ini", "group": "G", "key": "K", "value": "v"})
        unset = self.h.call("config.unset", {"file": "u.ini", "group": "G", "key": "K"})
        self.assertTrue(unset["ok"], unset)
        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        got = self.h.call("config.get", {"file": "u.ini", "group": "G", "key": "K"})
        self.assertEqual(got["result"]["value"], "v")

    def test_rotina_rejeita_calendario_com_quebra_de_linha(self) -> None:
        bad = self.h.call(
            "routine.create",
            {"name": "x", "calendar": "daily\nExecStartPre=/bin/sh -c oi", "argv": ["notify-send", "oi"]},
        )
        self.assertFalse(bad["ok"])

    def test_kwin_remove_tem_undo_por_fields(self) -> None:
        rule_file = str(self.h.home / ".local/share/agenticos/assets/Transparencia-Global.kwinrule")
        self.h.call("kwin.add_rule", {"file": rule_file}, yes=True)
        removed = self.h.call("kwin.remove_rule", {"description": "Transparência Global"}, yes=True)
        self.assertTrue(removed["ok"])
        undone = self.h.call("undo.last")
        self.assertTrue(undone["ok"], undone)
        rules = self.h.call("kwin.list_rules")["result"]["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["description"], "Transparência Global")
        rc = (self.h.home / ".config/kwinrulesrc").read_text(encoding="utf-8")
        self.assertIn("opacityactive=94", rc)

    def test_kwinrules_preserva_conteudo_ao_editar(self) -> None:
        rc = self.h.home / ".config/kwinrulesrc"
        rc.write_text(
            "# comentário do usuário\n"
            "[General]\n"
            "count=1\n"
            "rules=aaa-bbb\n"
            "\n"
            "[aaa-bbb]\n"
            "Description=Regra do usuário\n"
            "Enabled=false\n",
            encoding="utf-8",
        )
        rule_file = str(self.h.home / ".local/share/agenticos/assets/Transparencia-Global.kwinrule")
        self.h.call("kwin.add_rule", {"file": rule_file}, yes=True)
        text = rc.read_text(encoding="utf-8")
        self.assertIn("# comentário do usuário", text)
        self.assertIn("Description=Regra do usuário", text)
        self.assertIn("Enabled=false", text)
        rules = self.h.call("kwin.list_rules")["result"]["rules"]
        self.assertEqual(len(rules), 2)

    def test_plano_amarelo_e_auditado(self) -> None:
        self.h.call("theme.apply_preset")
        tail = self.h.call("audit.tail", {"n": 20})["result"]["entries"]
        plans = [entry for entry in tail if entry.get("event") == "plan"]
        self.assertTrue(plans, "pedido de plano deve entrar na auditoria")
        self.assertEqual(plans[-1]["action"], "theme.apply_preset")

    def test_resultados_grandes_do_daemon(self) -> None:
        big = self.h.home / "grande.txt"
        big.write_text("x" * 70000, encoding="utf-8")
        read = self.h.call("fs.read", {"path": str(big)})
        self.assertTrue(read["ok"], read)
        self.assertTrue(read["result"]["truncated"])
        self.assertEqual(len(read["result"]["content"]), 64 * 1024)


if __name__ == "__main__":
    unittest.main()
