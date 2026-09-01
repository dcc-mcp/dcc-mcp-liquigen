#include "bridge_contract.h"
#include "command_set.h"

#include <Windows.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace liquigen::command_bridge {
namespace {

constexpr std::ptrdiff_t kUiContextOffset = 0x18;
constexpr std::ptrdiff_t kTriggeredCommandsOffset = 0x188;
constexpr std::size_t kMaximumImageBytes = 512ULL * 1024ULL * 1024ULL;
constexpr std::size_t kGraphFunctionPatchBytes = 19;
constexpr std::size_t kProjectFramePatchBytes = 17;
constexpr std::size_t kGraphCommandGuardOffset = 0x458F;
constexpr ULONGLONG kGraphDispatchDeadlineMs = 3500;

constexpr unsigned char kAppStatePattern[] = {
    0x48, 0x8B, 0x0D, 0x00, 0x00, 0x00, 0x00,
    0x48, 0x8D, 0xB4, 0x24, 0x20, 0x01, 0x00, 0x00,
    0x48, 0x89, 0xF2,
};
constexpr char kAppStateMask[] = "xxx????xxxxxxxxxxx";

constexpr unsigned char kGraphFunctionPattern[] = {
    0x41, 0x56, 0x56, 0x57, 0x55, 0x53, 0x48, 0x81, 0xEC, 0x20,
    0x01, 0x00, 0x00, 0x4C, 0x89, 0xC6, 0x48, 0x89, 0xD3,
};
constexpr char kGraphFunctionMask[] = "xxxxxxxxxxxxxxxxxxx";

constexpr unsigned char kGraphConsumerPattern[] = {
    0x41, 0x57, 0x41, 0x56, 0x41, 0x55, 0x41, 0x54, 0x56, 0x57,
    0x55, 0x53, 0x48, 0x81, 0xEC, 0xB8, 0x0E, 0x00, 0x00,
};
constexpr char kGraphConsumerMask[] = "xxxxxxxxxxxxxxxxxxx";

constexpr unsigned char kGraphLayoutPattern[] = {
    0x31, 0xC0, 0x48, 0x83, 0x3D, 0x00, 0x00, 0x00, 0x00, 0x01,
    0x0F, 0x95, 0xC0, 0x48, 0x89, 0x05, 0x00, 0x00, 0x00, 0x00,
};
constexpr char kGraphLayoutMask[] = "xxxxx????xxxxxxx????";

constexpr unsigned char kProjectFramePattern[] = {
    0x55, 0x41, 0x57, 0x41, 0x56, 0x41, 0x54, 0x56, 0x57, 0x53,
    0x48, 0x81, 0xEC, 0xC0, 0x02, 0x00, 0x00, 0x48, 0x8D, 0xAC,
    0x24, 0x80, 0x00, 0x00, 0x00,
};
constexpr char kProjectFrameMask[] = "xxxxxxxxxxxxxxxxxxxxxxxxx";

constexpr unsigned char kProjectLoaderPattern[] = {
    0x41, 0x57, 0x41, 0x56, 0x41, 0x54, 0x56, 0x57, 0x55, 0x53,
    0x48, 0x81, 0xEC, 0x70, 0x01, 0x00, 0x00, 0x0F, 0x29, 0xB4,
    0x24, 0x60, 0x01, 0x00, 0x00, 0x48, 0x89, 0xD6,
};
constexpr char kProjectLoaderMask[] = "xxxxxxxxxxxxxxxxxxxxxxxxxxxx";

// The title-bar Home button and "Return to Project" button both toggle the same
// host-owned byte. Resolve both RIP-relative operands and require them to point
// at one writable byte before changing the requested state.
constexpr unsigned char kProjectPaletteStatePattern[] = {
    0x84, 0xDB, 0x74, 0x0E, 0x80, 0x3D, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x0F, 0x94, 0x05, 0x00, 0x00, 0x00, 0x00,
};
constexpr char kProjectPaletteStateMask[] = "xxxxxx????xxxx????";

using GraphFunction = void (*)(void*, void*, void*);
using ProjectFrameFunction = void (*)(void*, void*, void*);
using ProjectLoadFunction = bool (*)(const OdinString*, void*);

unsigned char* g_graph_function = nullptr;
GraphFunction g_graph_trampoline = nullptr;
unsigned char g_graph_original[kGraphFunctionPatchBytes]{};
unsigned char* g_graph_command_guard = nullptr;
volatile LONG g_graph_command_id = 0;
std::uint64_t g_graph_nonce = 0;
const char* g_graph_command_data = nullptr;
std::size_t g_graph_command_size = 0;
ULONGLONG g_graph_deadline = 0;
LONG g_graph_attempts = 0;
volatile LONG64* g_graph_layout = nullptr;
LONG64 g_graph_previous_layout = 0;
HWND g_graph_window = nullptr;
CommandSet* g_graph_command_set = nullptr;
bool g_graph_inserted = false;

unsigned char* g_project_frame_function = nullptr;
ProjectFrameFunction g_project_frame_trampoline = nullptr;
unsigned char g_project_frame_original[kProjectFramePatchBytes]{};
ProjectLoadFunction g_project_loader = nullptr;
volatile LONG g_project_command_id = 0;
std::uint64_t g_project_nonce = 0;
char g_project_path[kMaximumPayloadBytes]{};
std::size_t g_project_path_size = 0;
ULONGLONG g_project_deadline = 0;
HWND g_project_window = nullptr;

struct ModuleView {
    unsigned char* base;
    std::size_t image_size;
    unsigned char* text;
    std::size_t text_size;
    unsigned char* read_only_data;
    std::size_t read_only_data_size;
};

bool IsMapped(const void* pointer, std::size_t size, bool require_write) noexcept {
    if (pointer == nullptr || size == 0) {
        return false;
    }
    MEMORY_BASIC_INFORMATION information{};
    if (VirtualQuery(pointer, &information, sizeof(information)) != sizeof(information) ||
        information.State != MEM_COMMIT || (information.Protect & PAGE_GUARD) != 0 ||
        information.Protect == PAGE_NOACCESS) {
        return false;
    }
    const auto begin = reinterpret_cast<std::uintptr_t>(pointer);
    const auto region_begin = reinterpret_cast<std::uintptr_t>(information.BaseAddress);
    const auto region_end = region_begin + information.RegionSize;
    if (begin < region_begin || size > region_end - begin) {
        return false;
    }
    if (!require_write) {
        return true;
    }
    constexpr DWORD kWritable = PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE |
                                PAGE_EXECUTE_WRITECOPY;
    return (information.Protect & kWritable) != 0;
}

bool IsUsableCommandSet(CommandSet* command_set) noexcept {
    if (!IsMapped(command_set, sizeof(CommandSet), true) ||
        command_set->encoded_table == 0 || command_set->count < 0) {
        return false;
    }
    const auto exponent = command_set->encoded_table & 0x3F;
    if (exponent >= sizeof(std::size_t) * 8) {
        return false;
    }
    const auto capacity = std::size_t{1} << exponent;
    const auto table_base = command_set->encoded_table & ~std::uintptr_t{0x3F};
    return capacity != 0 && capacity <= 4096 &&
           static_cast<std::uint64_t>(command_set->count) <= capacity &&
           IsMapped(
               reinterpret_cast<void*>(table_base),
               capacity * (sizeof(OdinString) + sizeof(std::uint64_t) * 2),
               true);
}

bool GetLiquiGenModule(ModuleView* result) noexcept {
    if (result == nullptr) {
        return false;
    }
    wchar_t image_path[32768]{};
    const auto length = GetModuleFileNameW(nullptr, image_path, ARRAYSIZE(image_path));
    if (length == 0 || length >= ARRAYSIZE(image_path)) {
        return false;
    }
    const wchar_t* name = image_path;
    for (const wchar_t* cursor = image_path; *cursor != L'\0'; ++cursor) {
        if (*cursor == L'\\' || *cursor == L'/') {
            name = cursor + 1;
        }
    }
    if (_wcsicmp(name, L"LiquiGen.exe") != 0) {
        return false;
    }
    auto* base = reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr));
    if (!IsMapped(base, sizeof(IMAGE_DOS_HEADER), false)) {
        return false;
    }
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) {
        return false;
    }
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (!IsMapped(nt, sizeof(*nt), false) || nt->Signature != IMAGE_NT_SIGNATURE ||
        nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
        nt->OptionalHeader.SizeOfImage == 0 ||
        nt->OptionalHeader.SizeOfImage > kMaximumImageBytes) {
        return false;
    }
    result->base = base;
    result->image_size = nt->OptionalHeader.SizeOfImage;
    result->text = nullptr;
    result->text_size = 0;
    result->read_only_data = nullptr;
    result->read_only_data_size = 0;
    const auto* section = IMAGE_FIRST_SECTION(nt);
    for (unsigned index = 0; index < nt->FileHeader.NumberOfSections; ++index) {
        char name_buffer[9]{};
        std::memcpy(name_buffer, section[index].Name, 8);
        auto* section_base = base + section[index].VirtualAddress;
        const auto section_size = static_cast<std::size_t>(section[index].Misc.VirtualSize);
        if (std::strcmp(name_buffer, ".text") == 0) {
            result->text = section_base;
            result->text_size = section_size;
        } else if (std::strcmp(name_buffer, ".rdata") == 0) {
            result->read_only_data = section_base;
            result->read_only_data_size = section_size;
        }
    }
    return result->text != nullptr && result->text_size >= sizeof(kAppStatePattern) &&
           result->read_only_data != nullptr && result->read_only_data_size != 0;
}

unsigned char* FindPattern(
    unsigned char* begin,
    std::size_t size,
    const unsigned char* pattern,
    const char* mask,
    std::size_t pattern_size) noexcept {
    unsigned char* match = nullptr;
    std::size_t matches = 0;
    for (std::size_t offset = 0; offset + pattern_size <= size; ++offset) {
        bool equal = true;
        for (std::size_t index = 0; index < pattern_size; ++index) {
            if (mask[index] == 'x' && begin[offset + index] != pattern[index]) {
                equal = false;
                break;
            }
        }
        if (equal) {
            match = begin + offset;
            ++matches;
        }
    }
    return matches == 1 ? match : nullptr;
}

volatile LONG64* FindGraphLayoutSlot(const ModuleView& module) noexcept {
    volatile LONG64* slot = nullptr;
    for (std::size_t offset = 0;
         offset + sizeof(kGraphLayoutPattern) <= module.text_size;
         ++offset) {
        bool equal = true;
        for (std::size_t index = 0; index < sizeof(kGraphLayoutPattern); ++index) {
            if (kGraphLayoutMask[index] == 'x' &&
                module.text[offset + index] != kGraphLayoutPattern[index]) {
                equal = false;
                break;
            }
        }
        if (!equal) {
            continue;
        }
        auto* match = module.text + offset;
        std::int32_t displacement = 0;
        std::memcpy(&displacement, match + 5, sizeof(displacement));
        auto* candidate = reinterpret_cast<volatile LONG64*>(
            match + 10 + displacement);
        if (!IsMapped(const_cast<LONG64*>(candidate), sizeof(LONG64), true)) {
            return nullptr;
        }
        if (slot != nullptr && slot != candidate) {
            return nullptr;
        }
        slot = candidate;
    }
    return slot;
}

const char* FindCommandLiteral(const ModuleView& module, std::string_view command) noexcept {
    if (command.empty() || command.size() >= module.read_only_data_size) {
        return nullptr;
    }
    for (std::size_t offset = 0;
         offset + command.size() < module.read_only_data_size;
         ++offset) {
        if (std::memcmp(module.read_only_data + offset, command.data(), command.size()) != 0) {
            continue;
        }
        const auto trailing = module.read_only_data[offset + command.size()];
        const auto leading = offset == 0 ? static_cast<unsigned char>(0)
                                         : module.read_only_data[offset - 1];
        const auto is_name_character = [](unsigned char value) noexcept {
            return (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') ||
                   (value >= '0' && value <= '9') || value == '_' || value == '-';
        };
        if (!is_name_character(leading) && !is_name_character(trailing)) {
            return reinterpret_cast<const char*>(module.read_only_data + offset);
        }
    }
    return nullptr;
}

CommandSet* FindTriggeredCommandSet(const ModuleView& module) noexcept {
    auto* match = FindPattern(
        module.text,
        module.text_size,
        kAppStatePattern,
        kAppStateMask,
        sizeof(kAppStatePattern));
    if (match == nullptr) {
        return nullptr;
    }
    std::int32_t displacement = 0;
    std::memcpy(&displacement, match + 3, sizeof(displacement));
    auto** app_state_slot = reinterpret_cast<void**>(match + 7 + displacement);
    if (!IsMapped(app_state_slot, sizeof(void*), false) || *app_state_slot == nullptr ||
        !IsMapped(*app_state_slot, kUiContextOffset + sizeof(void*), false)) {
        return nullptr;
    }
    auto* app_state = reinterpret_cast<unsigned char*>(*app_state_slot);
    auto* ui_context = *reinterpret_cast<unsigned char**>(app_state + kUiContextOffset);
    if (!IsMapped(ui_context, kTriggeredCommandsOffset + sizeof(CommandSet), true)) {
        return nullptr;
    }
    auto* command_set = reinterpret_cast<CommandSet*>(ui_context + kTriggeredCommandsOffset);
    return IsUsableCommandSet(command_set) ? command_set : nullptr;
}

bool IsGraphScoped(CommandId id) noexcept {
    switch (id) {
        case CommandId::kExportAll:
        case CommandId::kExportSelected:
        case CommandId::kPlayTimeline:
        case CommandId::kPauseTimeline:
        case CommandId::kCenterGraph:
        case CommandId::kResetGraphZoom:
        case CommandId::kCenterGraphOnSelection:
            return true;
        default:
            return false;
    }
}

bool IsProjectPaletteStateCommand(CommandId id) noexcept {
    return id == CommandId::kShowProjectPalette || id == CommandId::kReturnToProject;
}

BridgeStatus SetProjectPaletteState(
    const ModuleView& module,
    CommandId id,
    HWND window) noexcept {
    if (!IsProjectPaletteStateCommand(id)) {
        return BridgeStatus::kUnknownCommand;
    }
    auto* match = FindPattern(
        module.text,
        module.text_size,
        kProjectPaletteStatePattern,
        kProjectPaletteStateMask,
        sizeof(kProjectPaletteStatePattern));
    if (match == nullptr) {
        return BridgeStatus::kProfileMismatch;
    }
    std::int32_t compare_displacement = 0;
    std::int32_t store_displacement = 0;
    std::memcpy(&compare_displacement, match + 6, sizeof(compare_displacement));
    std::memcpy(&store_displacement, match + 14, sizeof(store_displacement));
    auto* compare_target = match + 11 + compare_displacement;
    auto* store_target = match + 18 + store_displacement;
    if (compare_target != store_target || !IsMapped(compare_target, 1, true)) {
        return BridgeStatus::kProfileMismatch;
    }
    const char desired = id == CommandId::kShowProjectPalette ? 1 : 0;
    InterlockedExchange8(reinterpret_cast<volatile char*>(compare_target), desired);
    if (*reinterpret_cast<volatile char*>(compare_target) != desired) {
        return BridgeStatus::kNotConsumed;
    }
    InvalidateRect(window, nullptr, FALSE);
    PostMessageW(window, WM_PAINT, 0, 0);
    return BridgeStatus::kConsumed;
}

BridgeStatus Inject(CommandId id) noexcept;

void PublishBridgeStatus(
    CommandId id,
    std::uint64_t nonce,
    BridgeStatus status,
    std::uint32_t attempts) noexcept {
    if (id == CommandId::kInvalid || nonce == 0) {
        return;
    }
    wchar_t mapping_name[192]{};
    wchar_t event_name[192]{};
    MakeObjectName(mapping_name, ARRAYSIZE(mapping_name), GetCurrentProcessId(), nonce, L"state");
    MakeObjectName(event_name, ARRAYSIZE(event_name), GetCurrentProcessId(), nonce, L"event");
    const auto mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, mapping_name);
    if (mapping != nullptr) {
        auto* state = static_cast<SharedState*>(
            MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedState)));
        if (state != nullptr) {
            if (state->magic == kBridgeMagic && state->abi_version == kBridgeAbiVersion &&
                state->command_id == static_cast<std::uint32_t>(id)) {
                state->reserved = attempts;
                InterlockedExchange(&state->status, static_cast<LONG>(status));
            }
            UnmapViewOfFile(state);
        }
        CloseHandle(mapping);
    }
    const auto event = OpenEventW(EVENT_MODIFY_STATE, FALSE, event_name);
    if (event != nullptr) {
        SetEvent(event);
        CloseHandle(event);
    }
}

void RestoreGraphDetour() noexcept {
    if (g_graph_command_guard != nullptr) {
        DWORD previous = 0;
        if (VirtualProtect(g_graph_command_guard + 2, 1, PAGE_EXECUTE_READWRITE, &previous)) {
            g_graph_command_guard[2] = 0x74;
            FlushInstructionCache(GetCurrentProcess(), g_graph_command_guard + 2, 1);
            DWORD ignored = 0;
            VirtualProtect(g_graph_command_guard + 2, 1, previous, &ignored);
        }
        g_graph_command_guard = nullptr;
    }
    if (g_graph_function == nullptr) {
        if (g_graph_layout != nullptr) {
            InterlockedExchange64(g_graph_layout, g_graph_previous_layout);
            g_graph_layout = nullptr;
        }
        g_graph_window = nullptr;
        if (g_graph_trampoline != nullptr) {
            VirtualFree(reinterpret_cast<void*>(g_graph_trampoline), 0, MEM_RELEASE);
            g_graph_trampoline = nullptr;
        }
        return;
    }
    DWORD previous = 0;
    if (VirtualProtect(
            g_graph_function,
            kGraphFunctionPatchBytes,
            PAGE_EXECUTE_READWRITE,
            &previous)) {
        std::memcpy(
            g_graph_function,
            g_graph_original,
            kGraphFunctionPatchBytes);
        FlushInstructionCache(
            GetCurrentProcess(), g_graph_function, kGraphFunctionPatchBytes);
        DWORD ignored = 0;
        VirtualProtect(g_graph_function, kGraphFunctionPatchBytes, previous, &ignored);
    }
    g_graph_function = nullptr;
    if (g_graph_trampoline != nullptr) {
        VirtualFree(reinterpret_cast<void*>(g_graph_trampoline), 0, MEM_RELEASE);
        g_graph_trampoline = nullptr;
    }
    if (g_graph_layout != nullptr) {
        InterlockedExchange64(g_graph_layout, g_graph_previous_layout);
        g_graph_layout = nullptr;
    }
    g_graph_window = nullptr;
}

void CompleteGraphDispatch(BridgeStatus status) noexcept {
    const auto id = static_cast<CommandId>(InterlockedExchange(&g_graph_command_id, 0));
    const auto nonce = g_graph_nonce;
    if (status != BridgeStatus::kConsumed && g_graph_inserted &&
        g_graph_command_set != nullptr) {
        EraseCommand(g_graph_command_set, HostCommandName(id));
    }
    RestoreGraphDetour();
    PublishBridgeStatus(
        id, nonce, status, static_cast<std::uint32_t>(g_graph_attempts));
    g_graph_nonce = 0;
    g_graph_command_data = nullptr;
    g_graph_command_size = 0;
    g_graph_deadline = 0;
    g_graph_attempts = 0;
    g_graph_command_set = nullptr;
    g_graph_inserted = false;
}

void EnsureGraphDispatchCanRun(std::uint64_t nonce) noexcept {
    if (nonce == 0 || nonce != g_graph_nonce) {
        return;
    }
    if (g_graph_window != nullptr) {
        InvalidateRect(g_graph_window, nullptr, FALSE);
        PostMessageW(g_graph_window, WM_PAINT, 0, 0);
    }
}

void CancelGraphDispatch(std::uint64_t nonce) noexcept {
    if (nonce != 0 && nonce == g_graph_nonce && g_graph_command_id != 0) {
        CompleteGraphDispatch(BridgeStatus::kNotConsumed);
    }
}

void RestoreProjectFrameDetour() noexcept {
    if (g_project_frame_function != nullptr) {
        DWORD previous = 0;
        if (VirtualProtect(
                g_project_frame_function,
                kProjectFramePatchBytes,
                PAGE_EXECUTE_READWRITE,
                &previous)) {
            std::memcpy(
                g_project_frame_function,
                g_project_frame_original,
                kProjectFramePatchBytes);
            FlushInstructionCache(
                GetCurrentProcess(),
                g_project_frame_function,
                kProjectFramePatchBytes);
            DWORD ignored = 0;
            VirtualProtect(
                g_project_frame_function,
                kProjectFramePatchBytes,
                previous,
                &ignored);
        }
        g_project_frame_function = nullptr;
    }
    if (g_project_frame_trampoline != nullptr) {
        VirtualFree(
            reinterpret_cast<void*>(g_project_frame_trampoline),
            0,
            MEM_RELEASE);
        g_project_frame_trampoline = nullptr;
    }
}

void CompleteProjectOpen(BridgeStatus status) noexcept {
    const auto id = static_cast<CommandId>(InterlockedExchange(&g_project_command_id, 0));
    const auto nonce = g_project_nonce;
    RestoreProjectFrameDetour();
    PublishBridgeStatus(id, nonce, status, status == BridgeStatus::kConsumed ? 1U : 0U);
    g_project_loader = nullptr;
    g_project_nonce = 0;
    g_project_path[0] = '\0';
    g_project_path_size = 0;
    g_project_deadline = 0;
    g_project_window = nullptr;
}

void EnsureProjectOpenCanRun(std::uint64_t nonce) noexcept {
    if (nonce == 0 || nonce != g_project_nonce) {
        return;
    }
    if (g_project_window != nullptr) {
        InvalidateRect(g_project_window, nullptr, FALSE);
        PostMessageW(g_project_window, WM_PAINT, 0, 0);
    }
}

void CancelProjectOpen(std::uint64_t nonce) noexcept {
    if (nonce != 0 && nonce == g_project_nonce && g_project_command_id != 0) {
        CompleteProjectOpen(BridgeStatus::kNotConsumed);
    }
}

void ProjectFrameHook(void* app_state, void* context, void* frame) noexcept {
    const auto original = g_project_frame_trampoline;
    const auto id = static_cast<CommandId>(g_project_command_id);
    if (original == nullptr || id != CommandId::kProjectOpenPath) {
        if (original != nullptr) {
            original(app_state, context, frame);
        }
        return;
    }
    BridgeStatus status = BridgeStatus::kProfileMismatch;
    if (IsMapped(app_state, kUiContextOffset + sizeof(void*), false) &&
        g_project_loader != nullptr && g_project_path_size != 0) {
        const OdinString path{
            g_project_path,
            static_cast<std::int64_t>(g_project_path_size),
        };
        status = g_project_loader(&path, frame) ? BridgeStatus::kConsumed
                                                : BridgeStatus::kNotConsumed;
    }
    original(app_state, context, frame);
    CompleteProjectOpen(status);
}

BridgeStatus BeginProjectOpen(
    const ModuleView& module,
    CommandId id,
    std::uint64_t nonce,
    HWND window,
    const char* path,
    std::size_t path_size) noexcept {
    if (id != CommandId::kProjectOpenPath || path == nullptr || path_size == 0 ||
        path_size >= kMaximumPayloadBytes) {
        return BridgeStatus::kInternalError;
    }
    if (InterlockedCompareExchange(
            &g_project_command_id,
            static_cast<LONG>(id),
            0) != 0) {
        return BridgeStatus::kAlreadyPending;
    }
    auto* frame_target = FindPattern(
        module.text,
        module.text_size,
        kProjectFramePattern,
        kProjectFrameMask,
        sizeof(kProjectFramePattern));
    auto* loader_match = FindPattern(
        module.text,
        module.text_size,
        kProjectLoaderPattern,
        kProjectLoaderMask,
        sizeof(kProjectLoaderPattern));
    if (frame_target == nullptr || loader_match == nullptr) {
        InterlockedExchange(&g_project_command_id, 0);
        return BridgeStatus::kProfileMismatch;
    }
    if (!IsMapped(loader_match, sizeof(kProjectLoaderPattern), false)) {
        InterlockedExchange(&g_project_command_id, 0);
        return BridgeStatus::kProfileMismatch;
    }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&ProjectFrameHook),
            &pinned)) {
        InterlockedExchange(&g_project_command_id, 0);
        return BridgeStatus::kInternalError;
    }
    auto* trampoline = static_cast<unsigned char*>(VirtualAlloc(
        nullptr,
        kProjectFramePatchBytes + 12,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_EXECUTE_READWRITE));
    if (trampoline == nullptr) {
        InterlockedExchange(&g_project_command_id, 0);
        return BridgeStatus::kInternalError;
    }
    std::memcpy(g_project_frame_original, frame_target, kProjectFramePatchBytes);
    std::memcpy(trampoline, g_project_frame_original, kProjectFramePatchBytes);
    auto* cursor = trampoline + kProjectFramePatchBytes;
    cursor[0] = 0x48;
    cursor[1] = 0xB8;
    const auto continuation = reinterpret_cast<std::uintptr_t>(
        frame_target + kProjectFramePatchBytes);
    std::memcpy(cursor + 2, &continuation, sizeof(continuation));
    cursor[10] = 0xFF;
    cursor[11] = 0xE0;

    g_project_frame_function = frame_target;
    g_project_frame_trampoline = reinterpret_cast<ProjectFrameFunction>(trampoline);
    g_project_loader = reinterpret_cast<ProjectLoadFunction>(loader_match);
    std::memcpy(g_project_path, path, path_size);
    g_project_path[path_size] = '\0';
    g_project_path_size = path_size;
    g_project_nonce = nonce;
    g_project_deadline = GetTickCount64() + kGraphDispatchDeadlineMs;
    g_project_window = window;

    unsigned char patch[kProjectFramePatchBytes]{};
    patch[0] = 0x48;
    patch[1] = 0xB8;
    const auto hook = reinterpret_cast<std::uintptr_t>(&ProjectFrameHook);
    std::memcpy(patch + 2, &hook, sizeof(hook));
    patch[10] = 0xFF;
    patch[11] = 0xE0;
    std::memset(patch + 12, 0x90, kProjectFramePatchBytes - 12);
    DWORD previous = 0;
    if (!VirtualProtect(
            frame_target,
            kProjectFramePatchBytes,
            PAGE_EXECUTE_READWRITE,
            &previous)) {
        CompleteProjectOpen(BridgeStatus::kInternalError);
        return BridgeStatus::kInternalError;
    }
    std::memcpy(frame_target, patch, sizeof(patch));
    FlushInstructionCache(GetCurrentProcess(), frame_target, sizeof(patch));
    DWORD ignored = 0;
    VirtualProtect(frame_target, kProjectFramePatchBytes, previous, &ignored);
    InvalidateRect(window, nullptr, FALSE);
    PostMessageW(window, WM_PAINT, 0, 0);
    return BridgeStatus::kPending;
}

void GraphDispatchHook(
    void* ui_context,
    void* graph,
    void* frame) noexcept {
    const auto original = g_graph_trampoline;
    const auto id = static_cast<CommandId>(g_graph_command_id);
    if (original == nullptr || id == CommandId::kInvalid) {
        if (original != nullptr) {
            original(ui_context, graph, frame);
        }
        return;
    }
    BridgeStatus dispatch_status = BridgeStatus::kPending;
    auto* frame_bytes = static_cast<unsigned char*>(ui_context);
    auto* frame_command_set = IsMapped(
                                  frame_bytes,
                                  kTriggeredCommandsOffset + sizeof(CommandSet),
                                  true)
                                  ? reinterpret_cast<CommandSet*>(
                                        frame_bytes + kTriggeredCommandsOffset)
                                  : nullptr;
    if (!IsUsableCommandSet(frame_command_set)) {
        dispatch_status = BridgeStatus::kMapUnavailable;
    } else if (frame_command_set != g_graph_command_set) {
        const auto insertion = InsertCommand(
            frame_command_set,
            g_graph_command_data,
            g_graph_command_size);
        if (insertion != InsertResult::kInserted &&
            insertion != InsertResult::kAlreadyPresent) {
            dispatch_status = insertion == InsertResult::kFull
                                  ? BridgeStatus::kMapFull
                                  : BridgeStatus::kMapUnavailable;
        } else {
            if (g_graph_inserted && g_graph_command_set != nullptr) {
                EraseCommand(g_graph_command_set, HostCommandName(id));
            }
            g_graph_command_set = frame_command_set;
            g_graph_inserted = insertion == InsertResult::kInserted;
        }
    }

    original(ui_context, graph, frame);
    if (dispatch_status != BridgeStatus::kPending) {
        CompleteGraphDispatch(dispatch_status);
        return;
    }
    if (g_graph_command_set != nullptr &&
        !ContainsCommand(g_graph_command_set, HostCommandName(id))) {
        CompleteGraphDispatch(BridgeStatus::kConsumed);
        return;
    }
    ++g_graph_attempts;
    if (g_graph_attempts >= 240 || GetTickCount64() >= g_graph_deadline) {
        CompleteGraphDispatch(BridgeStatus::kNotConsumed);
    }
}

BridgeStatus BeginGraphDispatch(
    const ModuleView& module,
    CommandId id,
    std::uint64_t nonce,
    HWND window) noexcept {
    if (InterlockedCompareExchange(
            &g_graph_command_id,
            static_cast<LONG>(id),
            0) != 0) {
        return BridgeStatus::kAlreadyPending;
    }
    auto* target = FindPattern(
        module.text,
        module.text_size,
        kGraphFunctionPattern,
        kGraphFunctionMask,
        sizeof(kGraphFunctionPattern));
    auto* consumer = FindPattern(
        module.text,
        module.text_size,
        kGraphConsumerPattern,
        kGraphConsumerMask,
        sizeof(kGraphConsumerPattern));
    const auto command = HostCommandName(id);
    const auto* literal = FindCommandLiteral(module, command);
    auto* command_set = FindTriggeredCommandSet(module);
    auto* layout = FindGraphLayoutSlot(module);
    if (target == nullptr || consumer == nullptr || literal == nullptr || layout == nullptr ||
        command_set == nullptr) {
        InterlockedExchange(&g_graph_command_id, 0);
        return BridgeStatus::kProfileMismatch;
    }
    auto* command_guard = consumer + kGraphCommandGuardOffset;
    constexpr unsigned char kExpectedGuard[] = {0x84, 0xDB, 0x74, 0x0F};
    if (std::memcmp(command_guard, kExpectedGuard, sizeof(kExpectedGuard)) != 0) {
        InterlockedExchange(&g_graph_command_id, 0);
        return BridgeStatus::kProfileMismatch;
    }
    const auto insert = InsertCommand(command_set, literal, command.size());
    if (insert == InsertResult::kAlreadyPresent) {
        InterlockedExchange(&g_graph_command_id, 0);
        return BridgeStatus::kAlreadyPending;
    }
    if (insert != InsertResult::kInserted) {
        InterlockedExchange(&g_graph_command_id, 0);
        return insert == InsertResult::kFull ? BridgeStatus::kMapFull
                                             : BridgeStatus::kMapUnavailable;
    }
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(
            GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&GraphDispatchHook),
            &pinned)) {
        EraseCommand(command_set, command);
        InterlockedExchange(&g_graph_command_id, 0);
        return BridgeStatus::kInternalError;
    }
    auto* trampoline = static_cast<unsigned char*>(VirtualAlloc(
        nullptr,
        kGraphFunctionPatchBytes + 12,
        MEM_COMMIT | MEM_RESERVE,
        PAGE_EXECUTE_READWRITE));
    if (trampoline == nullptr) {
        EraseCommand(command_set, command);
        InterlockedExchange(&g_graph_command_id, 0);
        return BridgeStatus::kInternalError;
    }
    std::memcpy(g_graph_original, target, kGraphFunctionPatchBytes);
    std::memcpy(trampoline, g_graph_original, kGraphFunctionPatchBytes);
    auto* cursor = trampoline + kGraphFunctionPatchBytes;
    cursor[0] = 0x48;
    cursor[1] = 0xB8;
    const auto continuation = reinterpret_cast<std::uintptr_t>(
        target + kGraphFunctionPatchBytes);
    std::memcpy(cursor + 2, &continuation, sizeof(continuation));
    cursor[10] = 0xFF;
    cursor[11] = 0xE0;
    g_graph_trampoline = reinterpret_cast<GraphFunction>(trampoline);
    g_graph_function = target;
    g_graph_command_guard = command_guard;
    g_graph_layout = layout;
    g_graph_previous_layout = InterlockedExchange64(g_graph_layout, 1);
    g_graph_window = window;
    g_graph_nonce = nonce;
    g_graph_command_data = literal;
    g_graph_command_size = command.size();
    g_graph_command_set = command_set;
    g_graph_inserted = true;
    g_graph_deadline = GetTickCount64() + kGraphDispatchDeadlineMs;
    g_graph_attempts = 0;

    unsigned char patch[kGraphFunctionPatchBytes]{};
    patch[0] = 0x48;
    patch[1] = 0xB8;
    const auto hook = reinterpret_cast<std::uintptr_t>(&GraphDispatchHook);
    std::memcpy(patch + 2, &hook, sizeof(hook));
    patch[10] = 0xFF;
    patch[11] = 0xE0;
    std::memset(patch + 12, 0x90, kGraphFunctionPatchBytes - 12);
    DWORD previous = 0;
    if (!VirtualProtect(target, kGraphFunctionPatchBytes, PAGE_EXECUTE_READWRITE, &previous)) {
        EraseCommand(command_set, command);
        RestoreGraphDetour();
        InterlockedExchange(&g_graph_command_id, 0);
        g_graph_command_set = nullptr;
        g_graph_inserted = false;
        return BridgeStatus::kInternalError;
    }
    std::memcpy(target, patch, sizeof(patch));
    FlushInstructionCache(GetCurrentProcess(), target, sizeof(patch));
    DWORD ignored = 0;
    VirtualProtect(target, kGraphFunctionPatchBytes, previous, &ignored);
    previous = 0;
    if (!VirtualProtect(command_guard + 2, 1, PAGE_EXECUTE_READWRITE, &previous)) {
        CompleteGraphDispatch(BridgeStatus::kInternalError);
        return BridgeStatus::kInternalError;
    }
    command_guard[2] = 0xEB;
    FlushInstructionCache(GetCurrentProcess(), command_guard + 2, 1);
    VirtualProtect(command_guard + 2, 1, previous, &ignored);
    InvalidateRect(window, nullptr, FALSE);
    PostMessageW(window, WM_PAINT, 0, 0);
    return BridgeStatus::kPending;
}

BridgeStatus Inject(CommandId id) noexcept {
    const auto command = HostCommandName(id);
    if (command.empty()) {
        return BridgeStatus::kUnknownCommand;
    }
    ModuleView module{};
    if (!GetLiquiGenModule(&module)) {
        return BridgeStatus::kInvalidTarget;
    }
    auto* match = FindPattern(
        module.text,
        module.text_size,
        kAppStatePattern,
        kAppStateMask,
        sizeof(kAppStatePattern));
    if (match == nullptr) {
        return BridgeStatus::kProfileMismatch;
    }
    std::int32_t displacement = 0;
    std::memcpy(&displacement, match + 3, sizeof(displacement));
    auto** app_state_slot = reinterpret_cast<void**>(match + 7 + displacement);
    if (!IsMapped(app_state_slot, sizeof(void*), false) || *app_state_slot == nullptr ||
        !IsMapped(*app_state_slot, kUiContextOffset + sizeof(void*), false)) {
        return BridgeStatus::kProfileMismatch;
    }
    auto* app_state = reinterpret_cast<unsigned char*>(*app_state_slot);
    auto* ui_context = *reinterpret_cast<unsigned char**>(app_state + kUiContextOffset);
    if (!IsMapped(ui_context, kTriggeredCommandsOffset + sizeof(CommandSet), true)) {
        return BridgeStatus::kMapUnavailable;
    }
    auto* command_set = reinterpret_cast<CommandSet*>(ui_context + kTriggeredCommandsOffset);
    if (!IsUsableCommandSet(command_set)) {
        return BridgeStatus::kMapUnavailable;
    }
    const auto* stable_command = FindCommandLiteral(module, command);
    if (stable_command == nullptr) {
        return BridgeStatus::kProfileMismatch;
    }
    switch (InsertCommand(command_set, stable_command, command.size())) {
        case InsertResult::kInserted:
            return BridgeStatus::kInjected;
        case InsertResult::kAlreadyPresent:
            return BridgeStatus::kAlreadyPending;
        case InsertResult::kFull:
            return BridgeStatus::kMapFull;
        case InsertResult::kUnavailable:
            return BridgeStatus::kMapUnavailable;
        case InsertResult::kInvalid:
            return BridgeStatus::kInternalError;
    }
    return BridgeStatus::kInternalError;
}

void ProcessBridgeMessage(HWND window, CommandId id, std::uint64_t nonce) noexcept {
    wchar_t mapping_name[192]{};
    wchar_t event_name[192]{};
    MakeObjectName(mapping_name, ARRAYSIZE(mapping_name), GetCurrentProcessId(), nonce, L"state");
    MakeObjectName(event_name, ARRAYSIZE(event_name), GetCurrentProcessId(), nonce, L"event");
    const auto mapping = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, mapping_name);
    if (mapping == nullptr) {
        return;
    }
    auto* state = static_cast<SharedState*>(
        MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedState)));
    if (state == nullptr) {
        CloseHandle(mapping);
        return;
    }
    if (state->magic == kBridgeMagic && state->abi_version == kBridgeAbiVersion &&
        state->status == static_cast<LONG>(BridgeStatus::kPending) &&
        state->command_id == static_cast<std::uint32_t>(id)) {
        if (IsProjectPaletteStateCommand(id)) {
            ModuleView module{};
            const auto status = GetLiquiGenModule(&module)
                                    ? SetProjectPaletteState(module, id, window)
                                    : BridgeStatus::kInvalidTarget;
            state->reserved = status == BridgeStatus::kConsumed ? 1U : 0U;
            InterlockedExchange(&state->status, static_cast<LONG>(status));
        } else if (id == CommandId::kProjectOpenPath) {
            ModuleView module{};
            const auto status = GetLiquiGenModule(&module)
                                    ? BeginProjectOpen(
                                          module,
                                          id,
                                          nonce,
                                          window,
                                          state->payload.data(),
                                          state->payload_size)
                                    : BridgeStatus::kInvalidTarget;
            if (status == BridgeStatus::kPending) {
                UnmapViewOfFile(state);
                CloseHandle(mapping);
                return;
            }
            InterlockedExchange(&state->status, static_cast<LONG>(status));
        } else if (IsGraphScoped(id)) {
            ModuleView module{};
            const auto status = GetLiquiGenModule(&module)
                                    ? BeginGraphDispatch(module, id, nonce, window)
                                    : BridgeStatus::kInvalidTarget;
            if (status == BridgeStatus::kPending) {
                UnmapViewOfFile(state);
                CloseHandle(mapping);
                return;
            }
            InterlockedExchange(&state->status, static_cast<LONG>(status));
        } else {
            const auto status = Inject(id);
            InterlockedExchange(&state->status, static_cast<LONG>(status));
        }
    }
    const auto event = OpenEventW(EVENT_MODIFY_STATE, FALSE, event_name);
    if (event != nullptr) {
        SetEvent(event);
        CloseHandle(event);
    }
    UnmapViewOfFile(state);
    CloseHandle(mapping);
}

}  // namespace
}  // namespace liquigen::command_bridge

extern "C" __declspec(dllexport) LRESULT CALLBACK LiquiGenCommandHookProc(
    int code,
    WPARAM w_param,
    LPARAM l_param) {
    if (code >= 0 && liquigen::command_bridge::g_graph_command_id != 0 &&
        GetTickCount64() >= liquigen::command_bridge::g_graph_deadline) {
        liquigen::command_bridge::CompleteGraphDispatch(
            liquigen::command_bridge::BridgeStatus::kNotConsumed);
    }
    if (code >= 0 && liquigen::command_bridge::g_project_command_id != 0 &&
        GetTickCount64() >= liquigen::command_bridge::g_project_deadline) {
        liquigen::command_bridge::CompleteProjectOpen(
            liquigen::command_bridge::BridgeStatus::kNotConsumed);
    }
    if (code >= 0 && w_param == PM_REMOVE && l_param != 0) {
        auto* message = reinterpret_cast<MSG*>(l_param);
        const auto bridge_message = RegisterWindowMessageW(
            liquigen::command_bridge::kMessageName);
        const auto wake_message = RegisterWindowMessageW(
            liquigen::command_bridge::kWakeMessageName);
        const auto cancel_message = RegisterWindowMessageW(
            liquigen::command_bridge::kCancelMessageName);
        if (bridge_message != 0 && message->message == bridge_message) {
            const auto id = static_cast<liquigen::command_bridge::CommandId>(message->wParam);
            const auto nonce = static_cast<std::uint64_t>(message->lParam);
            message->message = WM_NULL;
            liquigen::command_bridge::ProcessBridgeMessage(message->hwnd, id, nonce);
        } else if (wake_message != 0 && message->message == wake_message) {
            const auto nonce = static_cast<std::uint64_t>(message->lParam);
            message->message = WM_NULL;
            liquigen::command_bridge::EnsureGraphDispatchCanRun(nonce);
            liquigen::command_bridge::EnsureProjectOpenCanRun(nonce);
        } else if (cancel_message != 0 && message->message == cancel_message) {
            const auto nonce = static_cast<std::uint64_t>(message->lParam);
            message->message = WM_NULL;
            liquigen::command_bridge::CancelGraphDispatch(nonce);
            liquigen::command_bridge::CancelProjectOpen(nonce);
        }
    }
    return CallNextHookEx(nullptr, code, w_param, l_param);
}
