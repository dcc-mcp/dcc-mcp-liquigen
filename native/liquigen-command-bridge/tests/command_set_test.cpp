#include "command_set.h"
#include "bridge_contract.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <string_view>

using liquigen::command_bridge::CommandSet;
using liquigen::command_bridge::ContainsCommand;
using liquigen::command_bridge::EraseCommand;
using liquigen::command_bridge::InsertCommand;
using liquigen::command_bridge::InsertResult;
using liquigen::command_bridge::OdinString;
using liquigen::command_bridge::CommandId;
using liquigen::command_bridge::CommandName;
using liquigen::command_bridge::HostCommandName;
using liquigen::command_bridge::UsesGraphDispatch;
using liquigen::command_bridge::RequiresConsumerAcknowledgement;
using liquigen::command_bridge::ShouldCompleteGraphDispatch;

namespace {

struct alignas(64) Storage {
    std::array<OdinString, 8> keys{};
    std::array<std::uint64_t, 8> values{};
    std::array<std::uint64_t, 8> controls{};
};

bool Check(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
    }
    return condition;
}

}  // namespace

int main() {
    Storage storage{};
    const auto base = reinterpret_cast<std::uintptr_t>(&storage);
    CommandSet set{base | 3U, 0};
    constexpr std::string_view play = "play_timeline";
    constexpr std::string_view pause = "pause_timeline";

    if (!Check(
            InsertCommand(&set, play.data(), play.size()) == InsertResult::kInserted,
            "first command was not inserted") ||
        !Check(set.count == 1, "command count was not incremented") ||
        !Check(ContainsCommand(&set, play), "inserted command cannot be found") ||
        !Check(
            InsertCommand(&set, play.data(), play.size()) == InsertResult::kAlreadyPresent,
            "duplicate command was not detected") ||
        !Check(set.count == 1, "duplicate command changed the count") ||
        !Check(
            InsertCommand(&set, pause.data(), pause.size()) == InsertResult::kInserted,
            "second command was not inserted") ||
        !Check(ContainsCommand(&set, pause), "second command cannot be found") ||
        !Check(EraseCommand(&set, play), "inserted command was not erased") ||
        !Check(!ContainsCommand(&set, play), "erased command is still present") ||
        !Check(ContainsCommand(&set, pause), "erase damaged a neighboring command") ||
        !Check(set.count == 1, "erase did not decrement the command count") ||
        !Check(!ContainsCommand(&set, "export-all"), "unknown command was reported present") ||
        !Check(
            HostCommandName(CommandId::kSwitchTabToExport) == "switch-tab-to-export",
            "export-tab semantic command mapping changed") ||
        !Check(
            UsesGraphDispatch(CommandId::kExportAll),
            "export-all must run in the live project graph context") ||
        !Check(
            !RequiresConsumerAcknowledgement(CommandId::kExportAll),
            "export-all completion must be verified from fresh export files") ||
        !Check(
            !ShouldCompleteGraphDispatch(CommandId::kExportAll, true, 0),
            "an empty helper graph must not complete export-all dispatch") ||
        !Check(
            ShouldCompleteGraphDispatch(CommandId::kExportAll, true, 26),
            "a nonempty project graph may consume export-all") ||
        !Check(
            ShouldCompleteGraphDispatch(CommandId::kResetGraphZoom, true, 0),
            "ordinary graph commands may complete on an empty graph") ||
        !Check(
            UsesGraphDispatch(CommandId::kPlayTimeline),
            "timeline playback must remain graph-consumer acknowledged") ||
        !Check(
            HostCommandName(CommandId::kResetSimulation) == "hard-reset" &&
                UsesGraphDispatch(CommandId::kResetSimulation),
            "simulation-reset semantic command mapping changed") ||
        !Check(
            HostCommandName(CommandId::kResetTimeline) == "reset" &&
                UsesGraphDispatch(CommandId::kResetTimeline),
            "timeline-reset semantic command mapping changed") ||
        !Check(
            HostCommandName(CommandId::kToggleFullscreenGraph) == "toggle-fullscreen-graph",
            "graph-view semantic command mapping changed") ||
        !Check(
            HostCommandName(CommandId::kToggleProjectPalette) == "open-project-palette",
            "project-palette semantic command mapping changed") ||
        !Check(
            CommandName(CommandId::kShowProjectPalette) == "show_project_palette" &&
                HostCommandName(CommandId::kShowProjectPalette).empty(),
            "show-project-palette state command mapping changed") ||
        !Check(
            CommandName(CommandId::kReturnToProject) == "return_to_project" &&
                HostCommandName(CommandId::kReturnToProject).empty(),
            "return-to-project state command mapping changed")) {
        return 1;
    }
    return 0;
}
