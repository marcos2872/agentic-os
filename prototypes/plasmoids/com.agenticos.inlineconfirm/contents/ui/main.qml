import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.plasma.plasmoid

// Plasmoid Plasma 6 (raiz obrigatoriamente PlasmoidItem).
// Espelha prototypes/InlineConfirmCard.qml, que segue como preview standalone via qmlscene.
// Protótipo: inline card de confirmação (ação amarela). Blur real via KWin; aqui opacidade.
PlasmoidItem {
    id: root

    Plasmoid.preferredRepresentation: Plasmoid.fullRepresentation

    Layout.preferredWidth: 380
    Layout.preferredHeight: 320
    width: 380
    height: 320

    property bool darkMode: true
    property bool reduceTransparency: false
    property bool highContrast: false

    // Tokens
    property real bgOpacity: highContrast || reduceTransparency ? 1.0 : (darkMode ? 0.68 : 0.58)
    property color glassColor: darkMode ? Qt.rgba(0.16, 0.17, 0.24, bgOpacity) : Qt.rgba(1, 1, 1, bgOpacity)
    property color strokeColor: highContrast ? (darkMode ? "#FFFFFF" : "#000000") : (darkMode ? "#ffffff2e" : "#00000024")
    property color textMain: highContrast ? (darkMode ? "#FFFFFF" : "#000000") : (darkMode ? "#EDEDF2" : "#1A1A1E")
    property color textMuted: highContrast ? textMain : (darkMode ? "#B8B8C4" : "#55555E")
    property int cardRadius: 16

    Rectangle {
        anchors.fill: parent
        color: "#1e1e2e"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            // Toggles de acessibilidade (demo)
            RowLayout {
                CheckBox { text: "Dark"; checked: root.darkMode; onToggled: root.darkMode = checked }
                CheckBox { text: "Reduzir transparência"; onToggled: root.reduceTransparency = checked }
                CheckBox { text: "Alto contraste"; onToggled: root.highContrast = checked }
            }

            // Glass card
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: root.cardRadius
                color: root.glassColor
                border.width: 1
                border.color: root.strokeColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8

                    Label {
                        text: "Instalar o Brave?"
                        color: root.textMain
                        font.pixelSize: 17
                        font.bold: true
                    }
                    Label {
                        text: "via Flatpak · flathub · +380 MB"
                        color: root.textMuted
                        font.pixelSize: 12
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 64
                        radius: 10
                        color: root.darkMode ? "#00000055" : "#0000000d"
                        border.width: 1
                        border.color: root.strokeColor
                        Label {
                            anchors.fill: parent
                            anchors.margins: 10
                            text: "diff: flatpak install flathub com.brave.Browser\nundo: flatpak uninstall com.brave.Browser"
                            color: root.textMuted
                            font.family: "monospace"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Button {
                            text: "Confirmar"
                            highlighted: true
                            Layout.fillWidth: true
                        }
                        Button { text: "Ver diff"; Layout.fillWidth: true }
                        Button { text: "Cancelar"; Layout.fillWidth: true }
                    }
                    Label {
                        text: "Ação amarela: exige confirmação. Texto puro funciona sem este card."
                        color: root.textMuted
                        font.pixelSize: 11
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
