#pragma once

#include <Windows.h>

#include <cstddef>
#include <cstdint>

#if defined(LG_UIA_BRIDGE_BUILD)
#define LG_UIA_API extern "C" __declspec(dllexport)
#else
#define LG_UIA_API extern "C" __declspec(dllimport)
#endif

#define LG_UIA_BRIDGE_ABI_VERSION 1u

enum LgUiaControlType : std::uint32_t {
    LG_UIA_CONTROL_PANE = 1,
    LG_UIA_CONTROL_TAB = 2,
    LG_UIA_CONTROL_TAB_ITEM = 3,
    LG_UIA_CONTROL_BUTTON = 4,
    LG_UIA_CONTROL_EDIT = 5,
    LG_UIA_CONTROL_TREE = 6,
    LG_UIA_CONTROL_TREE_ITEM = 7,
    LG_UIA_CONTROL_PROGRESS = 8,
};

enum LgUiaNodeFlags : std::uint32_t {
    LG_UIA_NODE_ENABLED = 1u << 0u,
    LG_UIA_NODE_FOCUSABLE = 1u << 1u,
    LG_UIA_NODE_FOCUSED = 1u << 2u,
    LG_UIA_NODE_INVOKE = 1u << 3u,
    LG_UIA_NODE_VALUE = 1u << 4u,
    LG_UIA_NODE_VALUE_READ_ONLY = 1u << 5u,
};

struct LgUiaRectV1 {
    double left;
    double top;
    double width;
    double height;
};

struct LgUiaNodeV1 {
    std::uint32_t struct_size;
    std::uint64_t id;
    std::uint64_t parent_id;
    LgUiaControlType control_type;
    std::uint32_t flags;
    const wchar_t* automation_id;
    const wchar_t* name;
    const wchar_t* value;
    LgUiaRectV1 bounds;
};

using LgUiaInvokeCallbackV1 = HRESULT(CALLBACK*)(void* context, std::uint64_t node_id);
using LgUiaSetValueCallbackV1 =
    HRESULT(CALLBACK*)(void* context, std::uint64_t node_id, const wchar_t* value);
using LgUiaSetFocusCallbackV1 = HRESULT(CALLBACK*)(void* context, std::uint64_t node_id);

struct LgUiaCallbacksV1 {
    std::uint32_t struct_size;
    void* context;
    LgUiaInvokeCallbackV1 invoke;
    LgUiaSetValueCallbackV1 set_value;
    LgUiaSetFocusCallbackV1 set_focus;
};

LG_UIA_API std::uint32_t WINAPI LgUiaBridgeAbiVersion();
LG_UIA_API HRESULT WINAPI LgUiaBridgeAttach(HWND window, const LgUiaCallbacksV1* callbacks);
LG_UIA_API HRESULT WINAPI LgUiaBridgePublish(
    const LgUiaNodeV1* nodes,
    std::size_t node_count,
    std::uint64_t generation);
LG_UIA_API HRESULT WINAPI LgUiaBridgeDetach();
