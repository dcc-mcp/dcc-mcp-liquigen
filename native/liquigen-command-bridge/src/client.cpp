#include "bridge_contract.h"

#include <Windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <string>
#include <string_view>

namespace liquigen::command_bridge {
namespace {

using HookProcedure = LRESULT(CALLBACK*)(int, WPARAM, LPARAM);

struct Arguments {
    DWORD pid = 0;
    HWND hwnd = nullptr;
    CommandId command = CommandId::kInvalid;
    DWORD timeout_ms = 5000;
    std::wstring project_path;
};

CommandId ParseCommand(std::wstring_view value) noexcept {
    for (const auto& command : kCommands) {
        std::wstring wide(command.semantic_name.begin(), command.semantic_name.end());
        if (value == wide) {
            return command.id;
        }
    }
    return CommandId::kInvalid;
}

bool ParseUnsigned(std::wstring_view value, unsigned long long* result) noexcept {
    if (value.empty() || result == nullptr) {
        return false;
    }
    wchar_t* end = nullptr;
    const std::wstring owned(value);
    const auto parsed = _wcstoui64(owned.c_str(), &end, 0);
    if (end == owned.c_str() || *end != L'\0') {
        return false;
    }
    *result = parsed;
    return true;
}

bool ParseArguments(int argc, wchar_t** argv, Arguments* result) noexcept {
    if (result == nullptr) {
        return false;
    }
    for (int index = 1; index < argc; ++index) {
        if (index + 1 >= argc) {
            return false;
        }
        const std::wstring_view option(argv[index]);
        const std::wstring_view value(argv[++index]);
        unsigned long long parsed = 0;
        if (option == L"--pid" && ParseUnsigned(value, &parsed) && parsed <= MAXDWORD) {
            result->pid = static_cast<DWORD>(parsed);
        } else if (option == L"--hwnd" && ParseUnsigned(value, &parsed)) {
            result->hwnd = reinterpret_cast<HWND>(static_cast<std::uintptr_t>(parsed));
        } else if (option == L"--command") {
            result->command = ParseCommand(value);
        } else if (option == L"--timeout-ms" && ParseUnsigned(value, &parsed) &&
                   parsed >= 100 && parsed <= 60000) {
            result->timeout_ms = static_cast<DWORD>(parsed);
        } else if (option == L"--project-path" && !value.empty()) {
            result->project_path = value;
        } else {
            return false;
        }
    }
    const auto requires_path = result->command == CommandId::kProjectOpenPath;
    return result->pid != 0 && result->hwnd != nullptr &&
           result->command != CommandId::kInvalid &&
           requires_path == !result->project_path.empty();
}

bool ProjectPathPayload(const std::wstring& path, std::string* result) noexcept {
    if (result == nullptr || path.empty()) {
        return false;
    }
    wchar_t resolved[32768]{};
    const auto length = GetFullPathNameW(path.c_str(), ARRAYSIZE(resolved), resolved, nullptr);
    if (length == 0 || length >= ARRAYSIZE(resolved)) {
        return false;
    }
    const auto attributes = GetFileAttributesW(resolved);
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0) {
        return false;
    }
    const auto* extension = wcsrchr(resolved, L'.');
    if (extension == nullptr || _wcsicmp(extension, L".liquigen") != 0) {
        return false;
    }
    const auto utf8_size = WideCharToMultiByte(
        CP_UTF8, WC_ERR_INVALID_CHARS, resolved, -1, nullptr, 0, nullptr, nullptr);
    if (utf8_size <= 1 || static_cast<std::size_t>(utf8_size) > kMaximumPayloadBytes) {
        return false;
    }
    result->resize(static_cast<std::size_t>(utf8_size));
    const auto converted = WideCharToMultiByte(
        CP_UTF8,
        WC_ERR_INVALID_CHARS,
        resolved,
        -1,
        result->data(),
        utf8_size,
        nullptr,
        nullptr);
    if (converted != utf8_size) {
        result->clear();
        return false;
    }
    result->resize(static_cast<std::size_t>(utf8_size - 1));
    return true;
}

std::wstring HookPath() {
    wchar_t path[32768]{};
    const auto length = GetModuleFileNameW(nullptr, path, ARRAYSIZE(path));
    if (length == 0 || length >= ARRAYSIZE(path)) {
        return {};
    }
    wchar_t* slash = wcsrchr(path, L'\\');
    if (slash == nullptr) {
        return {};
    }
    *(slash + 1) = L'\0';
    return std::wstring(path) + L"dcc_mcp_liquigen_command_hook.dll";
}

bool IsLiquiGenProcess(DWORD pid) noexcept {
    const auto process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (process == nullptr) {
        return false;
    }
    wchar_t path[32768]{};
    DWORD length = ARRAYSIZE(path);
    const auto ok = QueryFullProcessImageNameW(process, 0, path, &length);
    CloseHandle(process);
    if (!ok) {
        return false;
    }
    const wchar_t* name = path;
    for (const wchar_t* cursor = path; *cursor != L'\0'; ++cursor) {
        if (*cursor == L'\\' || *cursor == L'/') {
            name = cursor + 1;
        }
    }
    return _wcsicmp(name, L"LiquiGen.exe") == 0;
}

const char* StatusName(BridgeStatus status) noexcept {
    switch (status) {
        case BridgeStatus::kInjected:
            return "injected";
        case BridgeStatus::kAlreadyPending:
            return "already_pending";
        case BridgeStatus::kConsumed:
            return "consumed";
        case BridgeStatus::kProfileMismatch:
            return "profile_mismatch";
        case BridgeStatus::kInvalidTarget:
            return "invalid_target";
        case BridgeStatus::kMapUnavailable:
            return "command_map_unavailable";
        case BridgeStatus::kMapFull:
            return "command_map_full";
        case BridgeStatus::kUnknownCommand:
            return "unknown_command";
        case BridgeStatus::kInternalError:
            return "internal_error";
        case BridgeStatus::kNotConsumed:
            return "not_consumed";
        case BridgeStatus::kPending:
            return "timeout";
        case BridgeStatus::kEmpty:
            return "empty";
    }
    return "unknown";
}

int EmitFailure(const char* error, DWORD win32_error) noexcept {
    std::printf(
        "{\"success\":false,\"error\":\"%s\",\"win32_error\":%lu}\n",
        error,
        static_cast<unsigned long>(win32_error));
    return 1;
}

}  // namespace
}  // namespace liquigen::command_bridge

int wmain(int argc, wchar_t** argv) {
    using namespace liquigen::command_bridge;
    Arguments arguments{};
    if (!ParseArguments(argc, argv, &arguments)) {
        return EmitFailure("invalid_arguments", ERROR_INVALID_PARAMETER);
    }
    std::string payload;
    if (arguments.command == CommandId::kProjectOpenPath &&
        !ProjectPathPayload(arguments.project_path, &payload)) {
        return EmitFailure("invalid_project_path", ERROR_INVALID_NAME);
    }
    DWORD owner_pid = 0;
    const auto thread_id = GetWindowThreadProcessId(arguments.hwnd, &owner_pid);
    if (thread_id == 0 || owner_pid != arguments.pid || !IsLiquiGenProcess(arguments.pid)) {
        return EmitFailure("pid_hwnd_identity_mismatch", ERROR_INVALID_WINDOW_HANDLE);
    }
    const auto hook_path = HookPath();
    if (hook_path.empty()) {
        return EmitFailure("hook_path_unavailable", GetLastError());
    }
    const auto hook_module = LoadLibraryW(hook_path.c_str());
    if (hook_module == nullptr) {
        return EmitFailure("hook_load_failed", GetLastError());
    }
    const auto hook_proc = reinterpret_cast<HookProcedure>(
        GetProcAddress(hook_module, "LiquiGenCommandHookProc"));
    if (hook_proc == nullptr) {
        const auto error = GetLastError();
        FreeLibrary(hook_module);
        return EmitFailure("hook_export_missing", error);
    }

    LARGE_INTEGER counter{};
    QueryPerformanceCounter(&counter);
    const auto nonce = static_cast<std::uint64_t>(counter.QuadPart) ^
                       (static_cast<std::uint64_t>(GetTickCount64()) << 17U) ^ arguments.pid;
    wchar_t mapping_name[192]{};
    wchar_t event_name[192]{};
    MakeObjectName(mapping_name, ARRAYSIZE(mapping_name), arguments.pid, nonce, L"state");
    MakeObjectName(event_name, ARRAYSIZE(event_name), arguments.pid, nonce, L"event");
    const auto mapping = CreateFileMappingW(
        INVALID_HANDLE_VALUE,
        nullptr,
        PAGE_READWRITE,
        0,
        sizeof(SharedState),
        mapping_name);
    if (mapping == nullptr) {
        const auto error = GetLastError();
        FreeLibrary(hook_module);
        return EmitFailure("mapping_create_failed", error);
    }
    auto* state = static_cast<SharedState*>(
        MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SharedState)));
    if (state == nullptr) {
        const auto error = GetLastError();
        CloseHandle(mapping);
        FreeLibrary(hook_module);
        return EmitFailure("mapping_view_failed", error);
    }
    *state = {};
    state->magic = kBridgeMagic;
    state->abi_version = kBridgeAbiVersion;
    state->status = static_cast<LONG>(BridgeStatus::kPending);
    state->win32_error = ERROR_SUCCESS;
    state->command_id = static_cast<std::uint32_t>(arguments.command);
    state->payload_size = static_cast<std::uint32_t>(payload.size());
    if (!payload.empty()) {
        std::memcpy(state->payload.data(), payload.data(), payload.size());
    }
    const auto event = CreateEventW(nullptr, TRUE, FALSE, event_name);
    if (event == nullptr) {
        const auto error = GetLastError();
        UnmapViewOfFile(state);
        CloseHandle(mapping);
        FreeLibrary(hook_module);
        return EmitFailure("event_create_failed", error);
    }
    const auto hook = SetWindowsHookExW(WH_GETMESSAGE, hook_proc, hook_module, thread_id);
    if (hook == nullptr) {
        const auto error = GetLastError();
        CloseHandle(event);
        UnmapViewOfFile(state);
        CloseHandle(mapping);
        FreeLibrary(hook_module);
        return EmitFailure("hook_install_failed", error);
    }
    const auto message = RegisterWindowMessageW(kMessageName);
    const auto wake_message = RegisterWindowMessageW(kWakeMessageName);
    const auto cancel_message = RegisterWindowMessageW(kCancelMessageName);
    if (message == 0 || wake_message == 0 || cancel_message == 0 || !PostMessageW(
            arguments.hwnd,
            message,
            static_cast<WPARAM>(arguments.command),
            static_cast<LPARAM>(nonce))) {
        const auto error = GetLastError();
        UnhookWindowsHookEx(hook);
        CloseHandle(event);
        UnmapViewOfFile(state);
        CloseHandle(mapping);
        FreeLibrary(hook_module);
        return EmitFailure("bridge_message_failed", error);
    }
    const auto first_wait_ms = arguments.timeout_ms > 200 ? 100UL : arguments.timeout_ms / 2;
    auto wait_result = WaitForSingleObject(event, first_wait_ms);
    if (wait_result == WAIT_TIMEOUT &&
        state->status == static_cast<LONG>(BridgeStatus::kPending)) {
        PostMessageW(
            arguments.hwnd,
            wake_message,
            static_cast<WPARAM>(arguments.command),
            static_cast<LPARAM>(nonce));
        wait_result = WaitForSingleObject(event, arguments.timeout_ms - first_wait_ms);
    }
    if (wait_result == WAIT_TIMEOUT &&
        state->status == static_cast<LONG>(BridgeStatus::kPending)) {
        PostMessageW(
            arguments.hwnd,
            cancel_message,
            static_cast<WPARAM>(arguments.command),
            static_cast<LPARAM>(nonce));
        wait_result = WaitForSingleObject(event, 500);
    }
    const auto status = static_cast<BridgeStatus>(state->status);
    const auto graph_attempts = state->reserved;
    const auto graph_item_count = state->graph_item_count;
    const auto active_graph_item_count = state->active_graph_item_count;
    const auto accepted = status == BridgeStatus::kConsumed ||
                          (!RequiresConsumerAcknowledgement(arguments.command) &&
                           (status == BridgeStatus::kInjected ||
                            status == BridgeStatus::kAlreadyPending));
    UnhookWindowsHookEx(hook);
    CloseHandle(event);
    UnmapViewOfFile(state);
    CloseHandle(mapping);
    FreeLibrary(hook_module);
    if (wait_result != WAIT_OBJECT_0 && status == BridgeStatus::kPending) {
        return EmitFailure("bridge_timeout", wait_result == WAIT_FAILED ? GetLastError() : 0);
    }
    const auto command_name = CommandName(arguments.command);
    std::printf(
        "{\"success\":%s,\"interface\":\"liquigen.host.command.invoke.v1\","
        "\"command\":\"%.*s\",\"status\":\"%s\",\"pid\":%lu,"
        "\"hwnd\":%llu,\"ui_thread_id\":%lu,\"graph_attempts\":%lu,"
        "\"graph_item_count\":%lu,\"active_graph_item_count\":%lu,"
        "\"hash_required\":false}\n",
        accepted ? "true" : "false",
        static_cast<int>(command_name.size()),
        command_name.data(),
        StatusName(status),
        static_cast<unsigned long>(arguments.pid),
        static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(arguments.hwnd)),
        static_cast<unsigned long>(thread_id),
        static_cast<unsigned long>(graph_attempts),
        static_cast<unsigned long>(graph_item_count),
        static_cast<unsigned long>(active_graph_item_count));
    return accepted ? 0 : 1;
}
