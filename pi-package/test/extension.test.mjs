/**
 * Teste funcional da extensão agentic-os.ts fora do TUI.
 *
 * Roda dentro de uma pasta com node_modules contendo o pacote do pi
 * (ver run.sh): importa a extensão com jiti, injeta uma API falsa do pi e
 * um `agenticctl` falso, e valida registro das tools, fluxo amarelo
 * (confirmar/cancelar/sem UI/auto-confirm) e o guardrail de tools builtin.
 */

import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------- stub ctl
const work = mkdtempSync(join(tmpdir(), "pi-ext-"));
const ctlPath = join(work, "agenticctl");
const logPath = join(work, "ctl.log");
writeFileSync(
	ctlPath,
	`#!/usr/bin/env node
const fs = require("fs");
const args = process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(logPath)}, args.join(" ") + "\\n");
const action = args[1];
const hasConfirm = args.includes("--confirm");
if (action === "system.info") {
  console.log(JSON.stringify({ ok: true, risk: "green", result: { distro: { name: "Fedora Stub" } }, summary: "ok" }));
} else if (action === "fs.read") {
  console.log(JSON.stringify({ ok: true, risk: "green", result: { path: "/tmp/grande.txt", content: "x".repeat(70000) }, summary: "grande" }));
} else if (action === "theme.apply_preset" && !hasConfirm) {
  console.log(JSON.stringify({ ok: true, risk: "yellow", needs_confirmation: true, plan_id: "p1",
    plan: { action, explain: "aplicar tema escuro", params: {} } }));
} else if (action === "theme.apply_preset") {
  console.log(JSON.stringify({ ok: true, risk: "yellow", result: { preset: "dark-transparency" }, summary: "aplicado", undo_id: "u1" }));
} else {
  console.log(JSON.stringify({ ok: false, error: "ação desconhecida no stub" }));
}
`,
);
chmodSync(ctlPath, 0o755);
process.env.AGENTICOS_CTL = ctlPath;

// ------------------------------------------------------------- importação
const requireFromTest = createRequire(join(here, "package.json"));
const jitiModule = requireFromTest("jiti");
const jiti =
	typeof jitiModule === "function" ? jitiModule(import.meta.url) : jitiModule.createJiti(import.meta.url);
const loaded = typeof jiti.import === "function" ? await jiti.import(join(here, "agentic-os.ts")) : jiti(join(here, "agentic-os.ts"));
const factory = typeof loaded === "function" ? loaded : loaded.default;
assert.equal(typeof factory, "function", "extensão deve exportar uma factory default");

// ------------------------------------------------------------ API falsa
const tools = new Map();
const handlers = {};
const pi = {
	registerTool(tool) {
		tools.set(tool.name, tool);
	},
	on(event, handler) {
		handlers[event] = handler;
	},
};
factory(pi);

const expected = [
	"os_app_launch",
	"os_apps_install",
	"os_apps_installed",
	"os_apps_list",
	"os_apps_remove",
	"os_apps_search",
	"os_config_get",
	"os_config_set",
	"os_config_unset",
	"os_fs_read",
	"os_history",
	"os_kwin_rule_add",
	"os_kwin_rule_remove",
	"os_kwin_rules",
	"os_plasma_color_scheme",
	"os_plasma_wallpaper",
	"os_routine_create",
	"os_routine_list",
	"os_routine_remove",
	"os_routine_run",
	"os_service_user",
	"os_system_info",
	"os_theme_preset",
	"os_undo",
	"os_widget_install",
	"os_widget_list",
	"os_widget_remove",
].sort();
assert.deepEqual([...tools.keys()].sort(), expected, "tools registradas divergem do contrato");

const greenCtx = { hasUI: true, ui: { confirm: async () => true } };

// ------------------------------------------------------------- verde direto
{
	const result = await tools.get("os_system_info").execute("id", {}, null, null, greenCtx);
	assert.equal(result.isError, undefined);
	assert.match(result.content[0].text, /Fedora Stub/);
}

// ----------------------------------------------------- amarelo: confirmado
{
	const result = await tools.get("os_theme_preset").execute("id", {}, null, null, greenCtx);
	assert.equal(result.details.ok, true);
	assert.match(result.content[0].text, /aplicado/);
}

// ------------------------------------------------------- amarelo: cancelar
{
	const ctx = { hasUI: true, ui: { confirm: async () => false } };
	const result = await tools.get("os_theme_preset").execute("id", {}, null, null, ctx);
	assert.match(result.content[0].text, /cancelada/);
}

// ---------------------------------------------------------- amarelo: sem UI
{
	const result = await tools.get("os_theme_preset").execute("id", {}, null, null, { hasUI: false, ui: {} });
	assert.equal(result.isError, true);
	assert.match(result.content[0].text, /precisa de confirmação/);
}

// ------------------------------------------------- env AGENTICOS_AUTO_CONFIRM
{
	process.env.AGENTICOS_AUTO_CONFIRM = "1";
	const result = await tools.get("os_theme_preset").execute("id", {}, null, null, {});
	assert.match(result.content[0].text, /aplicado/);
	delete process.env.AGENTICOS_AUTO_CONFIRM;
}

// ---------------------------------------------------- resposta > 64 KiB
{
	const result = await tools.get("os_fs_read").execute("id", { path: "/tmp/grande.txt" }, null, null, {});
	assert.equal(result.isError, undefined, "resposta grande não pode quebrar o parse");
	assert.equal(result.details.ok, true);
	assert.match(result.content[0].text, /truncado/);
}

// ------------------------------------------------------- guardrail builtin
{
	const hook = handlers["tool_call"];
	assert.equal(typeof hook, "function", "hook tool_call deve estar registrado");
	const bash = await hook({ toolName: "bash", input: { command: "rm -rf /" } }, {});
	assert.equal(bash.block, true);
	const write = await hook({ toolName: "write", input: {} }, {});
	assert.equal(write.block, true);
	const read = await hook({ toolName: "read", input: {} }, {});
	assert.equal(read, undefined);
}

// ------------------------------------------------------- daemon indisponível
{
	process.env.AGENTICOS_CTL = join(work, "nao-existe");
	const result = await tools.get("os_system_info").execute("id", {}, null, null, greenCtx);
	assert.equal(result.isError, true);
	assert.match(result.content[0].text, /não consegui executar/);
}

console.log("extension.test.mjs: todas as asserções passaram ✓");
