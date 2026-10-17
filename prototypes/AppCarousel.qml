import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

// Protótipo: carousel de apps (render tool render_app_card)
// Modelo vem de structuredContent do daemon; seleção vai via update-model-context.
Rectangle {
    id: root
    width: 640
    height: 320
    color: "#1e1e2e"

    property bool darkMode: true
    property bool reduceTransparency: false
    property bool highContrast: false
    property int selectedIndex: 1

    property real bgOpacity: highContrast || reduceTransparency ? 1.0 : (darkMode ? 0.68 : 0.58)
    property color glassColor: darkMode ? Qt.rgba(0.16, 0.17, 0.24, bgOpacity) : Qt.rgba(1, 1, 1, bgOpacity)
    property color strokeColor: highContrast ? (darkMode ? "#FFFFFF" : "#000000") : (darkMode ? "#ffffff2e" : "#00000024")
    property color textMain: highContrast ? (darkMode ? "#FFFFFF" : "#000000") : (darkMode ? "#EDEDF2" : "#1A1A1E")
    property color textMuted: highContrast ? textMain : (darkMode ? "#B8B8C4" : "#55555E")

    ListModel {
        id: apps
        ListElement { name: "Brave"; detail: "flathub · 380 MB" }
        ListElement { name: "VS Code"; detail: "flathub · 420 MB" }
        ListElement { name: "Blender"; detail: "flathub · 510 MB" }
        ListElement { name: "GIMP"; detail: "flathub · 210 MB" }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            CheckBox { text: "Dark"; checked: root.darkMode; onToggled: root.darkMode = checked }
            CheckBox { text: "Reduzir transparência"; onToggled: root.reduceTransparency = checked }
            CheckBox { text: "Alto contraste"; onToggled: root.highContrast = checked }
            Label {
                text: "selecionado: " + apps.get(root.selectedIndex).name
                color: root.textMuted
                font.pixelSize: 12
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: ListView.Horizontal
            spacing: 12
            clip: true
            model: apps
            delegate: Rectangle {
                width: 180; height: 200
                radius: 16
                color: root.glassColor
                border.width: index === root.selectedIndex ? 2 : 1
                border.color: index === root.selectedIndex ? "#4da3ff" : root.strokeColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 12
                        color: root.darkMode ? "#ffffff1a" : "#00000012"
                        Label { anchors.centerIn: parent; text: model.name.charAt(0); color: root.textMain; font.pixelSize: 20; font.bold: true }
                    }
                    Label { text: model.name; color: root.textMain; font.pixelSize: 15; font.bold: true }
                    Label { text: model.detail; color: root.textMuted; font.pixelSize: 11 }
                    Button {
                        text: index === root.selectedIndex ? "Selecionado" : "Selecionar"
                        Layout.fillWidth: true
                        onClicked: root.selectedIndex = index
                    }
                }
                MouseArea { anchors.fill: parent; onClicked: root.selectedIndex = index }
            }
        }
        Label {
            text: "data tool flatpak_search → render tool render_app_card. Sem UI, o chat lista em texto."
            color: root.textMuted
            font.pixelSize: 11
        }
    }
}
