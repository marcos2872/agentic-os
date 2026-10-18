# Anatomia de um plasmoid (Plasma 6)

```
<nome>/
├── metadata.json
└── contents/ui/main.qml
```

## metadata.json (mínimo)

```json
{
  "KPackageStructure": "Plasma/Applet",
  "KPlugin": {
    "Authors": [{ "Name": "Agentic OS", "Email": "" }],
    "Category": "Utilities",
    "Description": "O que o widget faz",
    "EnabledByDefault": true,
    "Id": "com.agenticos.meu-widget",
    "License": "MIT",
    "Name": "Meu Widget",
    "Version": "1.0"
  },
  "X-Plasma-API-Minimum-Version": "6.0"
}
```

- O `Id` segue `com.agenticos.<nome>` e é o que aparece em `kpackagetool6 --list`.
- `Name` é o que o usuário busca na janela "Adicionar widgets".

## main.qml (mínimo que funciona)

```qml
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation

    fullRepresentation: Rectangle {
        implicitWidth: 260
        implicitHeight: 120
        radius: 16
        color: Qt.rgba(0.16, 0.17, 0.24, 0.68)   // vidro escuro
        border.width: 1
        border.color: "#ffffff2e"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 6
            Text { text: "Meu Widget"; color: "#EDEDF2"; font.bold: true }
            Text { text: "algo dinâmico aqui"; color: "#B8B8C4"; font.pixelSize: 12 }
        }
    }
}
```

## Dicas

- A raiz **obrigatoriamente** é `PlasmoidItem` (Plasma 6).
- Use `implicitWidth`/`implicitHeight` na representação; não use `anchors.fill` na raiz.
- Atualizar dados periodicamente: `Timer { interval: 1000; running: true; repeat: true;
  onTriggered: ... }`.
- Para reagir ao clique: `MouseArea { anchors.fill: parent; onClicked: ... }`.
- Imports seguros: `QtQuick`, `QtQuick.Layouts`, `QtQuick.Controls` (básico do Qt),
  `org.kde.plasma.plasmoid`. `org.kde.plasma.components` (botões/labels do Plasma) e
  `org.kde.kirigami` existem no Kinoite, mas evite se não precisar.
- JavaScript roda normalmente no QML (funções, `Date`, `Math`), mas **sem**
  `XMLHttpRequest` para arquivos locais e sem shell.
- Cores do tema `BreezeDark` usadas nos protótipos: fundo `#1e1e2e` (janela),
  vidro `Qt.rgba(0.16,0.17,0.24,0.68)`, texto `#EDEDF2`, texto secundário `#B8B8C4`.

## Testar (manual, o agente não roda shell)

```bash
plasmoidviewer -a com.agenticos.meu-widget        # pré-visualização
# ou: botão direito na área de trabalho → Adicionar widgets → buscar pelo nome
```

## Ciclo de vida no Agentic OS

1. `os_widget_create` → workspace com o esqueleto
2. `os_widget_write_file` → edições (arquivo completo por chamada)
3. `os_widget_lint` → metadata + qmllint
4. `os_widget_install path=...` → instala/atualiza
5. `os_widget_remove id=...` → remove (undo reinstala)
