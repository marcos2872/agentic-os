// @NAME@ — widget gerado pelo Agentic OS (edite pelo chat, sem shell).
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
        color: Qt.rgba(0.16, 0.17, 0.24, 0.68)
        border.width: 1
        border.color: "#ffffff2e"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 6

            Text {
                text: "@NAME@"
                color: "#EDEDF2"
                font.bold: true
                font.pixelSize: 16
            }
            Text {
                text: "Widget do Agentic OS"
                color: "#B8B8C4"
                font.pixelSize: 12
            }
        }
    }
}
