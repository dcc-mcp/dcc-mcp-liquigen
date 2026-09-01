#pragma once

#include <Windows.h>

#include <array>
#include <cstdint>
#include <string_view>

namespace liquigen::command_bridge {

inline constexpr std::uint32_t kBridgeMagic = 0x4C47434D;  // LGCM
inline constexpr std::uint32_t kBridgeAbiVersion = 3;
inline constexpr wchar_t kMessageName[] = L"DCC_MCP_LIQUIGEN_COMMAND_BRIDGE_V3";
inline constexpr wchar_t kWakeMessageName[] = L"DCC_MCP_LIQUIGEN_COMMAND_BRIDGE_WAKE_V3";
inline constexpr wchar_t kCancelMessageName[] = L"DCC_MCP_LIQUIGEN_COMMAND_BRIDGE_CANCEL_V3";
inline constexpr wchar_t kMappingPrefix[] = L"Local\\DccMcpLiquiGenCommandBridgeV3";
inline constexpr std::size_t kMaximumPayloadBytes = 4096;

enum class CommandId : std::uint32_t {
    kInvalid = 0,
    kProjectOpen = 1,
    kProjectSave = 2,
    kPlayTimeline = 3,
    kPauseTimeline = 4,
    kExportAll = 5,
    kExportSelected = 6,
    kOpenCommandPalette = 7,
    kSwitchTabToExport = 8,
    kSwitchTabToViewport = 9,
    kToggleFullscreenGraph = 10,
    kCenterGraph = 11,
    kResetGraphZoom = 13,
    kCenterGraphOnSelection = 14,
    kProjectOpenPath = 15,
    kToggleProjectPalette = 16,
    kShowProjectPalette = 17,
    kReturnToProject = 18,
    kResetSimulation = 19,
    kResetTimeline = 20,
};

enum class BridgeStatus : LONG {
    kEmpty = 0,
    kPending = 1,
    kInjected = 2,
    kAlreadyPending = 3,
    kConsumed = 4,
    kProfileMismatch = -1,
    kInvalidTarget = -2,
    kMapUnavailable = -3,
    kMapFull = -4,
    kUnknownCommand = -5,
    kInternalError = -6,
    kNotConsumed = -7,
};

struct SharedState {
    std::uint32_t magic;
    std::uint32_t abi_version;
    volatile LONG status;
    DWORD win32_error;
    std::uint32_t command_id;
    std::uint32_t reserved;
    std::uint32_t graph_item_count;
    std::uint32_t active_graph_item_count;
    std::uint32_t payload_size;
    std::array<char, kMaximumPayloadBytes> payload;
};

struct CommandDefinition {
    CommandId id;
    std::string_view semantic_name;
    std::string_view host_name;
};

inline constexpr std::array<CommandDefinition, 19> kCommands{{
    {CommandId::kProjectOpen, "project_open", "project-open"},
    {CommandId::kProjectSave, "project_save", "project-save"},
    {CommandId::kPlayTimeline, "play_timeline", "force-play"},
    {CommandId::kPauseTimeline, "pause_timeline", "pause"},
    {CommandId::kExportAll, "export_all", "export-all"},
    {CommandId::kExportSelected, "export_selected", "export-selected"},
    {CommandId::kOpenCommandPalette, "open_command_palette", "open-command-palette"},
    {CommandId::kSwitchTabToExport, "switch_tab_to_export", "switch-tab-to-export"},
    {CommandId::kSwitchTabToViewport, "switch_tab_to_viewport", "switch-tab-to-viewport"},
    {CommandId::kToggleFullscreenGraph, "toggle_fullscreen_graph", "toggle-fullscreen-graph"},
    {CommandId::kCenterGraph, "center_graph", "center-graph"},
    {CommandId::kResetGraphZoom, "reset_graph_zoom", "reset-graph-zoom"},
    {CommandId::kCenterGraphOnSelection, "center_graph_on_selection", "center-graph-on-selection"},
    {CommandId::kProjectOpenPath, "open_project_path", ""},
    {CommandId::kToggleProjectPalette, "toggle_project_palette", "open-project-palette"},
    {CommandId::kShowProjectPalette, "show_project_palette", ""},
    {CommandId::kReturnToProject, "return_to_project", ""},
    {CommandId::kResetSimulation, "reset_simulation", "hard-reset"},
    {CommandId::kResetTimeline, "reset_timeline", "reset"},
}};

inline constexpr std::string_view CommandName(CommandId id) noexcept {
    for (const auto& command : kCommands) {
        if (command.id == id) {
            return command.semantic_name;
        }
    }
    return {};
}

inline constexpr std::string_view HostCommandName(CommandId id) noexcept {
    for (const auto& command : kCommands) {
        if (command.id == id) {
            return command.host_name;
        }
    }
    return {};
}

inline constexpr bool UsesGraphDispatch(CommandId id) noexcept {
    switch (id) {
        case CommandId::kExportAll:
        case CommandId::kExportSelected:
        case CommandId::kPlayTimeline:
        case CommandId::kPauseTimeline:
        case CommandId::kResetSimulation:
        case CommandId::kResetTimeline:
        case CommandId::kCenterGraph:
        case CommandId::kResetGraphZoom:
        case CommandId::kCenterGraphOnSelection:
            return true;
        default:
            return false;
    }
}

inline constexpr bool RequiresConsumerAcknowledgement(CommandId id) noexcept {
    switch (id) {
        case CommandId::kPlayTimeline:
        case CommandId::kPauseTimeline:
        case CommandId::kResetSimulation:
        case CommandId::kResetTimeline:
        case CommandId::kCenterGraph:
        case CommandId::kResetGraphZoom:
        case CommandId::kCenterGraphOnSelection:
        case CommandId::kProjectOpenPath:
        case CommandId::kShowProjectPalette:
        case CommandId::kReturnToProject:
            return true;
        default:
            return false;
    }
}

inline constexpr bool ShouldCompleteGraphDispatch(
    CommandId id,
    bool command_was_consumed,
    std::uint32_t graph_item_count) noexcept {
    if (!command_was_consumed) {
        return false;
    }
    if (id == CommandId::kExportAll || id == CommandId::kExportSelected) {
        return graph_item_count > 0;
    }
    return true;
}

inline void MakeObjectName(
    wchar_t* destination,
    std::size_t destination_count,
    DWORD pid,
    std::uint64_t nonce,
    const wchar_t* suffix) {
    _snwprintf_s(
        destination,
        destination_count,
        _TRUNCATE,
        L"%s_%lu_%016llx_%s",
        kMappingPrefix,
        static_cast<unsigned long>(pid),
        static_cast<unsigned long long>(nonce),
        suffix);
}

}  // namespace liquigen::command_bridge
