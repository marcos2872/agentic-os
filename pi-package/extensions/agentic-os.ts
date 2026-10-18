/**
 * Agentic OS — tools de controle do sistema para o pi.
 *
 * Cada tool `os_*` chama o daemon de políticas (`agenticctl`) e obedece ao
 * contrato de risco:
 *  - verde: executa direto (o daemon audita e oferece undo);
 *  - amarela: o daemon devolve needs_confirmation + plan_id; a UI pergunta
 *    ao usuário via ctx.ui.confirm e, se aprovado, a ação é confirmada;
 *  - vermelha: o daemon bloqueia com explicação (a tool devolve o erro).
 *
 * Variáveis de ambiente:
 *  - AGENTICOS_CTL: caminho do CLI (padrão: `agenticctl` no PATH);
 *  - AGENTICOS_AUTO_CONFIRM=1: confirma ações amarelas sem perguntar
 *    (apenas para testes automatizados);
 *  - AGENTICOS_ALLOW_BUILTIN=1: modo confiança — libera bash/write/edit sem
 *    confirmação nenhuma (inclui padrões destrutivos). Use por sua conta.
 *
 * Ferramentas builtin (bash/write/edit/powershell):
 *  - Por padrão ficam ativas mas PASSAM por confirmação a cada uso (a UI do
 *    pi pergunta antes de executar). Sem UI, são bloqueadas (falha segura).
 *  - Mesmo confirmadas, padrões catastróficos em bash (sudo/pkexec, mexer na
 *    base do sistema, disco/partição, /etc crítico, rm em raiz/home) são
 *    bloqueados — para isso existe o modo confiança.
 *  - Escritas fora de $HOME, /tmp e /var/tmp são bloqueadas.
 *  - As ferramentas os_* continuam sendo o caminho preferido: têm auditoria,
 *    undo e o modelo de risco verde/amarelo/vermelho do daemon.
 */

import { spawn } from "node:child_process";
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CTL_FALLBACK = "agenticctl";
// fs.read devolve até 64 KiB de conteúdo numa única linha JSON (~90 KB);
// o limite protege contra respostas patológicas sem quebrar o caso normal.
const MAX_STDOUT_CHARS = 512 * 1024;
const MAX_RESULT_CHARS = 6000;

/** Resolve o CLI a cada chamada (permite trocar via env em runtime). */
function ctlPath(): string {
	return process.env.AGENTICOS_CTL ?? CTL_FALLBACK;
}

interface DaemonResponse {
	ok: boolean;
	risk?: "green" | "yellow" | "red";
	needs_confirmation?: boolean;
	plan_id?: string;
	plan?: { action?: string; summary?: string; explain?: string; params?: Record<string, unknown> };
	result?: unknown;
	error?: string;
	summary?: string;
	undo_id?: string | null;
}

interface ToolResultShape {
	content: Array<{ type: "text"; text: string }>;
	details: unknown;
	isError?: boolean;
}

interface ToolSpec {
	name: string;
	label: string;
	description: string;
	action: string;
	parameters: ReturnType<typeof Type.Object>;
	/** Converte parâmetros da tool nos parâmetros da ação do daemon. */
	toDaemon?: (params: Record<string, unknown>) => Record<string, unknown>;
}

function callDaemon(
	action: string,
	params: Record<string, unknown>,
	confirm?: string,
): Promise<DaemonResponse> {
	return new Promise((resolve, reject) => {
		const binary = ctlPath();
		const args = ["call", action, "--json", "--params-json", JSON.stringify(params)];
		if (confirm) {
			args.push("--confirm", confirm);
		}
		const child = spawn(binary, args, { stdio: ["ignore", "pipe", "pipe"] });
		let stdout = "";
		let stderr = "";
		let overflow = false;
		child.stdout.on("data", (chunk: Buffer) => {
			if (stdout.length >= MAX_STDOUT_CHARS) {
				overflow = true;
				return;
			}
			stdout += chunk.toString();
		});
		child.stderr.on("data", (chunk: Buffer) => {
			if (stderr.length < 2000) {
				stderr += chunk.toString();
			}
		});
		child.on("error", (error) => {
			reject(
				new Error(
					`não consegui executar ${binary}: ${error.message}. O daemon está instalado (setup/install.sh)?`,
				),
			);
		});
		child.on("close", () => {
			if (overflow) {
				reject(new Error(`resposta do daemon excedeu ${MAX_STDOUT_CHARS} caracteres`));
				return;
			}
			const line = stdout.trim().split("\n").pop() ?? "";
			try {
				resolve(JSON.parse(line) as DaemonResponse);
			} catch {
				reject(
					new Error(
						`resposta inválida do daemon: ${line.slice(0, 300)}${stderr ? ` | ${stderr.slice(0, 300)}` : ""}`,
					),
				);
			}
		});
	});
}

function truncate(text: string): string {
	if (text.length <= MAX_RESULT_CHARS) {
		return text;
	}
	return `${text.slice(0, MAX_RESULT_CHARS)}\n... resultado truncado (${text.length - MAX_RESULT_CHARS} chars omitidos)`;
}

function formatResponse(response: DaemonResponse): ToolResultShape {
	if (response.ok && !response.needs_confirmation) {
		const body = truncate(JSON.stringify(response.result ?? {}, null, 2));
		const undoHint = response.undo_id ? "\n\n(desfazível com os_undo)" : "";
		const head = response.summary ? `${response.summary}\n\n` : "";
		return {
			content: [{ type: "text", text: `${head}${body}${undoHint}` }],
			details: response,
		};
	}
	const reason = response.error ?? "erro desconhecido no daemon";
	return {
		content: [{ type: "text", text: `falhou: ${reason}` }],
		details: response,
		isError: true,
	};
}

async function runTool(
	spec: ToolSpec,
	params: Record<string, unknown>,
	ctx: any,
): Promise<ToolResultShape> {
	try {
		const daemonParams = spec.toDaemon ? spec.toDaemon(params) : params;
		const first = await callDaemon(spec.action, daemonParams);
		if (first.ok && first.needs_confirmation) {
			const explain = first.plan?.explain ?? first.plan?.summary ?? "ação amarela";
			if (!first.plan_id) {
				return formatResponse({ ...first, ok: false, error: "plano sem plan_id" });
			}
			if (process.env.AGENTICOS_AUTO_CONFIRM === "1") {
				const confirmed = await callDaemon(spec.action, daemonParams, first.plan_id);
				return formatResponse(confirmed);
			}
			const ui = ctx?.ui;
			if (!ui?.confirm) {
				return {
					content: [
						{
							type: "text",
							text: `ação amarela "${explain}" precisa de confirmação do usuário, mas esta sessão não tem UI. Rode o chat com interface ou defina AGENTICOS_AUTO_CONFIRM=1.`,
						},
					],
					details: first,
					isError: true,
				};
			}
			const detail = JSON.stringify(first.plan?.params ?? daemonParams, null, 2);
			const approved = await ui.confirm("Confirmar ação amarela?", `${explain}\n\nParâmetros:\n${detail}`);
			if (!approved) {
				return {
					content: [{ type: "text", text: `ação cancelada pelo usuário: ${explain}` }],
					details: { cancelled: true, ...first },
				};
			}
			const confirmed = await callDaemon(spec.action, daemonParams, first.plan_id);
			return formatResponse(confirmed);
		}
		return formatResponse(first);
	} catch (error) {
		return {
			content: [{ type: "text", text: `falhou: ${(error as Error).message}` }],
			details: { error: String(error) },
			isError: true,
		};
	}
}

const TOOLS: ToolSpec[] = [
	{
		name: "os_system_info",
		label: "System Info",
		description:
			"Informações do sistema: distro, kernel, base imutável, sessão gráfica e ferramentas disponíveis.",
		action: "system.info",
		parameters: Type.Object({}),
	},
	{
		name: "os_fs_read",
		label: "Ler arquivo",
		description:
			"Lê arquivo de texto (até 64 KiB) em $HOME, /etc, /var/log ou /tmp. Arquivos sensíveis (chaves, keyrings) são bloqueados.",
		action: "fs.read",
		parameters: Type.Object({
			path: Type.String({ description: "Caminho absoluto do arquivo." }),
		}),
	},
	{
		name: "os_apps_list",
		label: "Listar apps",
		description: "Lista aplicativos instalados (Flatpak + entradas .desktop), com filtro opcional por nome.",
		action: "apps.list",
		parameters: Type.Object({
			query: Type.Optional(Type.String({ description: "Filtro por nome (opcional)." })),
		}),
	},
	{
		name: "os_apps_installed",
		label: "Apps Flatpak instalados",
		description: "Lista os aplicativos Flatpak instalados (ID, nome, versão, origem). Use antes de remover.",
		action: "flatpak.list",
		parameters: Type.Object({}),
	},
	{
		name: "os_apps_search",
		label: "Buscar apps",
		description: "Busca aplicativos no remoto Flatpak (flathub) por termo. Use antes de instalar.",
		action: "flatpak.search",
		parameters: Type.Object({
			query: Type.String({ description: "Termo de busca (ex.: brave, gimp)." }),
		}),
	},
	{
		name: "os_apps_install",
		label: "Instalar app",
		description:
			"Instala aplicativo Flatpak pelo ID (escopo user por padrão; system exige confirmação). Reversível com os_undo.",
		action: "flatpak.install",
		parameters: Type.Object({
			app_id: Type.String({ description: "ID do app (ex.: com.brave.Browser)." }),
			remote: Type.Optional(Type.String({ description: "Remoto Flatpak (padrão: flathub)." })),
			scope: Type.Optional(Type.String({ description: "user (padrão) ou system." })),
		}),
	},
	{
		name: "os_apps_remove",
		label: "Remover app",
		description: "Desinstala aplicativo Flatpak pelo ID. Reversível com os_undo.",
		action: "flatpak.uninstall",
		parameters: Type.Object({
			app_id: Type.String({ description: "ID do app instalado." }),
			scope: Type.Optional(Type.String({ description: "user (padrão) ou system." })),
		}),
	},
	{
		name: "os_app_launch",
		label: "Abrir app",
		description: "Abre um aplicativo pelo ID .desktop ou nome (ex.: firefox, org.kde.konsole).",
		action: "apps.launch",
		parameters: Type.Object({
			app: Type.String({ description: "ID .desktop ou nome do app." }),
		}),
	},
	{
		name: "os_theme_preset",
		label: "Aplicar preset visual",
		description:
			"AMARELA: aplica o preset 'dark-transparency' — tema escuro (BreezeDark) + transparência global (regra KWin 94%). Reversível com os_undo.",
		action: "theme.apply_preset",
		parameters: Type.Object({
			preset: Type.Optional(Type.String({ description: "Preset (padrão: dark-transparency)." })),
			rule_file: Type.Optional(Type.String({ description: "Arquivo .kwinrule alternativo (opcional)." })),
		}),
	},
	{
		name: "os_plasma_color_scheme",
		label: "Esquema de cores",
		description: "AMARELA: troca o esquema de cores do Plasma (ex.: BreezeDark, BreezeLight).",
		action: "plasma.set_color_scheme",
		parameters: Type.Object({
			scheme: Type.String({ description: "Nome do esquema de cores." }),
		}),
	},
	{
		name: "os_plasma_wallpaper",
		label: "Papel de parede",
		description: "AMARELA: troca o papel de parede do Plasma para a imagem indicada.",
		action: "plasma.set_wallpaper",
		parameters: Type.Object({
			path: Type.String({ description: "Caminho absoluto da imagem (png/jpg/webp)." }),
		}),
	},
	{
		name: "os_kwin_rules",
		label: "Regras do KWin",
		description: "Lista as regras de janela do KWin (id, descrição, ativa).",
		action: "kwin.list_rules",
		parameters: Type.Object({}),
	},
	{
		name: "os_kwin_rule_add",
		label: "Adicionar regra KWin",
		description: "AMARELA: instala uma regra de janela do KWin a partir de um arquivo .kwinrule.",
		action: "kwin.add_rule",
		parameters: Type.Object({
			file: Type.Optional(Type.String({ description: "Caminho do arquivo .kwinrule." })),
			fields: Type.Optional(Type.Object({}, { description: "Campos da regra (uso interno do undo)." })),
			id: Type.Optional(Type.String({ description: "UUID ao restaurar uma regra (uso interno)." })),
			description: Type.Optional(Type.String({ description: "Descrição ao restaurar uma regra (uso interno)." })),
		}),
	},
	{
		name: "os_kwin_rule_remove",
		label: "Remover regra KWin",
		description: "AMARELA: remove regra de janela do KWin por id ou descrição. Reversível com os_undo.",
		action: "kwin.remove_rule",
		parameters: Type.Object({
			id: Type.Optional(Type.String({ description: "UUID da regra." })),
			description: Type.Optional(Type.String({ description: "Descrição da regra." })),
		}),
	},
	{
		name: "os_widget_list",
		label: "Listar widgets",
		description: "Lista os plasmoids instalados no usuário e os widgets em criação no workspace.",
		action: "widget.list",
		parameters: Type.Object({}),
	},
	{
		name: "os_widget_create",
		label: "Criar widget",
		description:
			"Cria o esqueleto de um widget (plasmoid) no workspace: metadata.json + contents/ui/main.qml. Depois use os_widget_write_file e os_widget_install.",
		action: "widget.scaffold",
		parameters: Type.Object({
			name: Type.String({ description: "Nome curto (a-z, 0-9, hífen)." }),
			description: Type.Optional(Type.String({ description: "Descrição mostrada no Plasma (até 120 chars)." })),
		}),
	},
	{
		name: "os_widget_write_file",
		label: "Escrever arquivo do widget",
		description:
			"Escreve/atualiza um arquivo dentro do workspace do widget (ex.: contents/ui/main.qml). Até 128 KiB; reversível com os_undo.",
		action: "widget.write_file",
		parameters: Type.Object({
			name: Type.String({ description: "Nome do widget no workspace." }),
			path: Type.String({ description: "Caminho relativo (ex.: contents/ui/main.qml)." }),
			content: Type.String({ description: "Conteúdo completo do arquivo." }),
		}),
	},
	{
		name: "os_widget_read_file",
		label: "Ler arquivo do widget",
		description: "Lê um arquivo do workspace do widget (padrão: contents/ui/main.qml).",
		action: "widget.read_file",
		parameters: Type.Object({
			name: Type.String({ description: "Nome do widget no workspace." }),
			path: Type.Optional(Type.String({ description: "Caminho relativo (padrão: contents/ui/main.qml)." })),
		}),
	},
	{
		name: "os_widget_lint",
		label: "Validar widget",
		description: "Valida o metadata.json e roda qmllint nos QML do widget; use antes de instalar.",
		action: "widget.lint",
		parameters: Type.Object({
			name: Type.String({ description: "Nome do widget no workspace." }),
		}),
	},
	{
		name: "os_widget_install",
		label: "Instalar widget",
		description:
			"Instala/atualiza um plasmoid a partir de um diretório local com metadata.json (em $HOME, /tmp ou /var/tmp). Reversível com os_undo.",
		action: "widget.install",
		parameters: Type.Object({
			path: Type.String({ description: "Diretório do plasmoid." }),
		}),
	},
	{
		name: "os_widget_remove",
		label: "Remover widget",
		description: "Remove um plasmoid instalado no usuário. Reversível com os_undo quando a origem é conhecida.",
		action: "widget.remove",
		parameters: Type.Object({
			id: Type.String({ description: "ID do plasmoid (ex.: com.agenticos.appcarousel)." }),
		}),
	},
	{
		name: "os_service_user",
		label: "Serviço do usuário",
		description:
			"Controla um serviço systemd --user: op=status lista estado; enable/disable/start/stop/restart mudam. enable/disable são reversíveis.",
		action: "service.user",
		parameters: Type.Object({
			unit: Type.String({ description: "Nome da unit (ex.: foo.timer)." }),
			op: Type.String({ description: "status, enable, disable, start, stop ou restart." }),
		}),
	},
	{
		name: "os_routine_list",
		label: "Listar rotinas",
		description: "Lista as rotinas (timers systemd --user criados pelo Agentic OS) com calendário e próxima execução.",
		action: "routine.list",
		parameters: Type.Object({}),
	},
	{
		name: "os_routine_create",
		label: "Criar rotina",
		description:
			"Cria uma rotina agendada (timer systemd --user). Comandos permitidos: flatpak [--user] update [-y], notify-send, kbuildsycoca6. Reversível com os_undo.",
		action: "routine.create",
		parameters: Type.Object({
			name: Type.String({ description: "Nome curto (a-z, 0-9, hífen)." }),
			calendar: Type.String({ description: "Expressão OnCalendar (ex.: 'Sun *-*-* 10:00')." }),
			argv: Type.Array(Type.String(), { description: "Comando permitido, ex.: ['flatpak','update','-y']." }),
		}),
	},
	{
		name: "os_routine_remove",
		label: "Remover rotina",
		description: "Remove uma rotina criada pelo Agentic OS. Reversível com os_undo.",
		action: "routine.remove",
		parameters: Type.Object({
			name: Type.String({ description: "Nome da rotina." }),
		}),
	},
	{
		name: "os_routine_run",
		label: "Executar rotina",
		description: "Executa a rotina agora (uma vez), sem esperar o horário agendado.",
		action: "routine.run",
		parameters: Type.Object({
			name: Type.String({ description: "Nome da rotina." }),
		}),
	},
	{
		name: "os_config_get",
		label: "Ler configuração",
		description: "Lê uma chave de arquivo INI em ~/.config (ex.: kdeglobals).",
		action: "config.get",
		parameters: Type.Object({
			file: Type.String({ description: "Caminho relativo em ~/.config (ex.: kdeglobals)." }),
			group: Type.String({ description: "Grupo INI." }),
			key: Type.String({ description: "Chave INI." }),
		}),
	},
	{
		name: "os_config_set",
		label: "Escrever configuração",
		description:
			"Escreve uma chave em arquivo INI de ~/.config (com backup automático). Reversível com os_undo. Não use para headless/segredos.",
		action: "config.set",
		parameters: Type.Object({
			file: Type.String({ description: "Caminho relativo em ~/.config." }),
			group: Type.String({ description: "Grupo INI." }),
			key: Type.String({ description: "Chave INI." }),
			value: Type.String({ description: "Valor (string)." }),
		}),
	},
	{
		name: "os_config_unset",
		label: "Remover configuração",
		description: "Remove uma chave de arquivo INI em ~/.config (com backup). Reversível com os_undo.",
		action: "config.unset",
		parameters: Type.Object({
			file: Type.String({ description: "Caminho relativo em ~/.config." }),
			group: Type.String({ description: "Grupo INI." }),
			key: Type.String({ description: "Chave INI." }),
		}),
	},
	{
		name: "os_undo",
		label: "Desfazer",
		description: "Desfaz a última ação reversível (instalação, config, regra, widget, rotina).",
		action: "undo.last",
		parameters: Type.Object({}),
	},
	{
		name: "os_history",
		label: "Histórico",
		description: "Mostra as últimas entradas da auditoria (quem pediu, risco, resultado).",
		action: "audit.tail",
		parameters: Type.Object({
			n: Type.Optional(Type.Integer({ description: "Quantidade (padrão 20, máx. 200)." })),
		}),
	},
];

export default function (pi: ExtensionAPI) {
	for (const spec of TOOLS) {
		pi.registerTool(
			defineTool({
				name: spec.name,
				label: spec.label,
				description: spec.description,
				parameters: spec.parameters,
				async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
					return runTool(spec, params as Record<string, unknown>, ctx);
				},
			}),
		);
	}

	// Guardrail das ferramentas builtin (bash/write/edit/powershell):
	// confirmação por uso + bloqueio de padrões catastróficos.
	pi.on("tool_call", async (event, ctx) => {
		if (!BUILTIN_GATE.has(event.toolName)) {
			return undefined;
		}
		if (process.env.AGENTICOS_ALLOW_BUILTIN === "1") {
			return undefined; // modo confiança
		}

		const input = (event.input ?? {}) as Record<string, unknown>;

		if (event.toolName === "bash" || event.toolName === "powershell") {
			const command = String(input.command ?? "");
			for (const rule of RED_COMMANDS) {
				if (rule.re.test(command)) {
					return {
						block: true,
						reason:
							`Agentic OS: comando bloqueado por segurança (${rule.why}). ` +
							"Se for realmente necessário, execute manualmente no terminal ou libere " +
							"o modo confiança (AGENTICOS_ALLOW_BUILTIN=1).",
					};
				}
			}
			return confirmBuiltin(ctx, `Rodar este comando no terminal?\n\n${command}`);
		}

		const path = findPath(input);
		if (path && !pathAllowed(path)) {
			return {
				block: true,
				reason:
					`Agentic OS: escrever fora de $HOME, /tmp ou /var/tmp não é permitido (${path}). ` +
					"Use o modo confiança somente se souber o que está fazendo.",
			};
		}
		return confirmBuiltin(ctx, `Gravar arquivo com ${event.toolName}?\n\n${path ?? "(caminho não identificado)"}`);
	});
}

// ------------------------------------------------------- guardrail (builtin)

const BUILTIN_GATE = new Set(["bash", "powershell", "edit", "write"]);

const RED_COMMANDS: Array<{ re: RegExp; why: string }> = [
	{ re: /(^|[;&|(]\s*)(sudo|doas|pkexec)\b/i, why: "escalada de privilégio" },
	{ re: /\b(mkfs\.?\w*|fdisk|parted|wipefs|blkdiscard)\b/i, why: "operação em disco/partição" },
	{ re: /\bdd\b[^\n]*\bof=\s*\/dev\//i, why: "escrita direta em dispositivo" },
	{ re: /\brm\s+(-[A-Za-z]+\s+)*(\/+|~|\$HOME|\.)\s*($|[;&|])/i, why: "remoção de raiz/home" },
	{
		re: /\b(rpm-ostree|dnf|rpm)\s+(install|remove|erase|update|upgrade|override|distro-sync)\b/i,
		why: "alteração na base do sistema",
	},
	{ re: /\/etc\/(pam\.d|shadow|gshadow|sudoers|fstab)/, why: "arquivo crítico do sistema" },
	{ re: /\/boot\//, why: "área de boot" },
];

function findPath(input: Record<string, unknown>): string | null {
	for (const key of ["file_path", "path", "file", "filename"]) {
		const value = input[key];
		if (typeof value === "string" && value.trim()) {
			return value.trim();
		}
	}
	return null;
}

function pathAllowed(raw: string): boolean {
	if (raw.includes("..")) {
		return false;
	}
	if (!raw.startsWith("/")) {
		return true; // relativo: resolve dentro do diretório de trabalho
	}
	const home = process.env.HOME ?? "";
	const roots = [home && `${home}/`, "/tmp/", "/var/tmp/"].filter(Boolean);
	return roots.some((root) => raw === root.slice(0, -1) || raw.startsWith(root));
}

async function confirmBuiltin(ctx: any, message: string): Promise<{ block: boolean; reason: string } | undefined> {
	const ui = ctx?.ui;
	if (!ctx?.hasUI || !ui?.select) {
		return {
			block: true,
			reason:
				"Agentic OS: sem UI para confirmar o uso de ferramentas de terminal/escrita. " +
				"Defina AGENTICOS_ALLOW_BUILTIN=1 para permitir sem confirmação.",
		};
	}
	const choice = await ui.select(`${message}\n\n(Agentic OS)`, ["Permitir", "Não"]);
	if (choice !== "Permitir") {
		return { block: true, reason: "Agentic OS: ação negada pelo usuário" };
	}
	return undefined;
}
