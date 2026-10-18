/**
 * Valida as skills do pacote (formato Agent Skills / pi):
 * frontmatter, nome = diretório, limites e referências existentes.
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const skillsRoot = join(here, "..", "skills");
const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const dirs = readdirSync(skillsRoot).filter((entry) => statSync(join(skillsRoot, entry)).isDirectory());
assert.ok(dirs.length >= 5, `esperado pelo menos 5 skills, encontrei ${dirs.length}`);

for (const dir of dirs) {
	const file = join(skillsRoot, dir, "SKILL.md");
	assert.ok(existsSync(file), `${dir}: SKILL.md ausente`);
	const text = readFileSync(file, "utf8");

	assert.ok(text.startsWith("---\n"), `${dir}: SKILL.md precisa começar com frontmatter`);
	const end = text.indexOf("\n---", 4);
	assert.ok(end > 0, `${dir}: frontmatter sem fechamento`);
	const front = text.slice(4, end);
	const body = text.slice(end + 4);

	const field = (key) => {
		const match = front.match(new RegExp(`^${key}:\\s*(.+)$`, "m"));
		return match ? match[1].trim() : null;
	};
	const name = field("name");
	const description = field("description");

	assert.ok(name, `${dir}: frontmatter sem 'name'`);
	assert.equal(name, dir, `${dir}: 'name' deve ser igual ao nome do diretório`);
	assert.ok(NAME_RE.test(name), `${dir}: 'name' inválido (use minúsculas e hífen)`);
	assert.ok(name.length <= 64, `${dir}: 'name' acima de 64 caracteres`);
	assert.ok(description, `${dir}: frontmatter sem 'description'`);
	assert.ok(description.length <= 1024, `${dir}: 'description' acima de 1024 caracteres`);
	assert.ok(/Use /.test(description), `${dir}: 'description' deve dizer quando usar ("Use ...")`);

	assert.ok(body.trim().length > 200, `${dir}: corpo da skill muito curto`);
	assert.ok(/os_[a-z_]+/.test(body), `${dir}: corpo não menciona nenhuma ferramenta os_*`);

	const refs = [...body.matchAll(/`(references\/[A-Za-z0-9._-]+)`/g)].map((match) => match[1]);
	for (const ref of new Set(refs)) {
		assert.ok(existsSync(join(skillsRoot, dir, ref)), `${dir}: referência quebrada: ${ref}`);
	}
}

console.log(`check-skills.mjs: ${dirs.length} skills válidas ✓`);
