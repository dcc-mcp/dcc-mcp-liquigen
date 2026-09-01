#include "liquigen_uia_bridge.h"

#include <Ole2.h>
#include <UIAutomation.h>

#include <atomic>
#include <iostream>
#include <string>
#include <thread>

namespace {

constexpr wchar_t kWindowClass[] = L"LiquiGenUiaBridgeContractWindow";
constexpr UINT kWorkerFinished = WM_APP + 41;

struct CallbackState {
    DWORD ui_thread_id = 0;
    std::atomic<int> invoke_count = 0;
    std::atomic<int> set_value_count = 0;
    std::atomic<bool> callback_thread_ok = true;
    std::wstring last_value;
};

HRESULT CALLBACK OnInvoke(void* context, std::uint64_t node_id) {
    auto* state = static_cast<CallbackState*>(context);
    if (node_id != 3u) {
        return E_INVALIDARG;
    }
    state->callback_thread_ok =
        state->callback_thread_ok.load() && GetCurrentThreadId() == state->ui_thread_id;
    ++state->invoke_count;
    return S_OK;
}

HRESULT CALLBACK OnSetValue(void* context, std::uint64_t node_id, const wchar_t* value) {
    auto* state = static_cast<CallbackState*>(context);
    if (node_id != 2u || value == nullptr) {
        return E_INVALIDARG;
    }
    state->callback_thread_ok =
        state->callback_thread_ok.load() && GetCurrentThreadId() == state->ui_thread_id;
    state->last_value = value;
    ++state->set_value_count;
    return S_OK;
}

HRESULT CALLBACK OnSetFocus(void* context, std::uint64_t) {
    auto* state = static_cast<CallbackState*>(context);
    state->callback_thread_ok =
        state->callback_thread_ok.load() && GetCurrentThreadId() == state->ui_thread_id;
    return S_OK;
}

LRESULT CALLBACK WindowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wparam, lparam);
}

HRESULT FindByAutomationId(
    IUIAutomation* automation,
    IUIAutomationElement* root,
    const wchar_t* automation_id,
    IUIAutomationElement** result) {
    VARIANT value;
    VariantInit(&value);
    value.vt = VT_BSTR;
    value.bstrVal = SysAllocString(automation_id);
    if (value.bstrVal == nullptr) {
        return E_OUTOFMEMORY;
    }
    IUIAutomationCondition* condition = nullptr;
    HRESULT hr = automation->CreatePropertyCondition(UIA_AutomationIdPropertyId, value, &condition);
    VariantClear(&value);
    if (FAILED(hr)) {
        return hr;
    }
    hr = root->FindFirst(TreeScope_Descendants, condition, result);
    condition->Release();
    return hr;
}

HRESULT ExerciseProvider(HWND window) {
    const char* stage = "CoInitializeEx";
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool uninitialize = SUCCEEDED(hr);
    if (hr == RPC_E_CHANGED_MODE) {
        hr = S_OK;
    }
    if (FAILED(hr)) {
        return hr;
    }

    IUIAutomation* automation = nullptr;
    IUIAutomationElement* root = nullptr;
    IUIAutomationElement* directory = nullptr;
    IUIAutomationElement* export_now = nullptr;
    IUIAutomationValuePattern* value_pattern = nullptr;
    IUIAutomationInvokePattern* invoke_pattern = nullptr;

    stage = "CoCreateInstance";
    hr = CoCreateInstance(
        __uuidof(CUIAutomation), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&automation));
    if (SUCCEEDED(hr)) {
        stage = "ElementFromHandle";
        hr = automation->ElementFromHandle(window, &root);
    }
    if (SUCCEEDED(hr)) {
        stage = "Find directory";
        hr = FindByAutomationId(automation, root, L"export.directory", &directory);
        if (SUCCEEDED(hr) && directory == nullptr) {
            hr = E_FAIL;
        }
    }
    if (SUCCEEDED(hr)) {
        stage = "Get Value pattern";
        hr = directory->GetCurrentPatternAs(UIA_ValuePatternId, IID_PPV_ARGS(&value_pattern));
    }
    if (SUCCEEDED(hr)) {
        stage = "Find export button";
        hr = FindByAutomationId(automation, root, L"export.now", &export_now);
        if (SUCCEEDED(hr) && export_now == nullptr) {
            hr = E_FAIL;
        }
    }
    if (SUCCEEDED(hr)) {
        stage = "Get Invoke pattern";
        hr = export_now->GetCurrentPatternAs(UIA_InvokePatternId, IID_PPV_ARGS(&invoke_pattern));
    }
    if (SUCCEEDED(hr)) {
        stage = "SetValue";
        BSTR directory_value = SysAllocString(L"F:\\exports\\liquigen");
        if (directory_value == nullptr) {
            hr = E_OUTOFMEMORY;
        } else {
            hr = value_pattern->SetValue(directory_value);
            SysFreeString(directory_value);
        }
    }
    if (SUCCEEDED(hr)) {
        stage = "Invoke";
        hr = invoke_pattern->Invoke();
    }

    if (FAILED(hr)) {
        std::cerr << "ExerciseProvider failed at " << stage << ": " << std::hex << hr << "\n";
    }

    if (invoke_pattern != nullptr) {
        invoke_pattern->Release();
    }
    if (value_pattern != nullptr) {
        value_pattern->Release();
    }
    if (export_now != nullptr) {
        export_now->Release();
    }
    if (directory != nullptr) {
        directory->Release();
    }
    if (root != nullptr) {
        root->Release();
    }
    if (automation != nullptr) {
        automation->Release();
    }
    if (uninitialize) {
        CoUninitialize();
    }
    return hr;
}

}  // namespace

int wmain() {
    const HINSTANCE instance = GetModuleHandleW(nullptr);
    WNDCLASSW window_class{};
    window_class.hInstance = instance;
    window_class.lpfnWndProc = WindowProc;
    window_class.lpszClassName = kWindowClass;
    if (RegisterClassW(&window_class) == 0) {
        std::cerr << "RegisterClassW failed\n";
        return 1;
    }

    HWND window = CreateWindowExW(
        0,
        kWindowClass,
        L"LiquiGen semantic bridge contract",
        WS_OVERLAPPEDWINDOW,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        800,
        600,
        nullptr,
        nullptr,
        instance,
        nullptr);
    if (window == nullptr) {
        std::cerr << "CreateWindowExW failed\n";
        return 1;
    }

    CallbackState state;
    state.ui_thread_id = GetCurrentThreadId();
    const LgUiaCallbacksV1 callbacks{
        sizeof(LgUiaCallbacksV1), &state, OnInvoke, OnSetValue, OnSetFocus};
    HRESULT hr = LgUiaBridgeAttach(window, &callbacks);
    if (FAILED(hr)) {
        std::cerr << "LgUiaBridgeAttach failed: " << std::hex << hr << "\n";
        return 1;
    }

    const LgUiaNodeV1 nodes[] = {
        {sizeof(LgUiaNodeV1),
         1,
         0,
         LG_UIA_CONTROL_PANE,
         LG_UIA_NODE_ENABLED,
         L"liquigen.root",
         L"LiquiGen",
         L"",
         {100, 100, 800, 600}},
        {sizeof(LgUiaNodeV1),
         2,
         1,
         LG_UIA_CONTROL_EDIT,
         LG_UIA_NODE_ENABLED | LG_UIA_NODE_FOCUSABLE | LG_UIA_NODE_VALUE,
         L"export.directory",
         L"Directory",
         L"",
         {500, 300, 260, 32}},
        {sizeof(LgUiaNodeV1),
         3,
         1,
         LG_UIA_CONTROL_BUTTON,
         LG_UIA_NODE_ENABLED | LG_UIA_NODE_FOCUSABLE | LG_UIA_NODE_INVOKE,
         L"export.now",
         L"Export Now",
         L"",
         {500, 350, 120, 32}},
    };

    LgUiaNodeV1 invalid_nodes[] = {nodes[0], nodes[1]};
    invalid_nodes[1].automation_id = L"liquigen.root";
    hr = LgUiaBridgePublish(invalid_nodes, std::size(invalid_nodes), 1);
    if (hr != E_INVALIDARG) {
        std::cerr << "duplicate AutomationId snapshot was not rejected\n";
        return 1;
    }
    hr = LgUiaBridgePublish(nodes, std::size(nodes), 1);
    if (FAILED(hr)) {
        std::cerr << "LgUiaBridgePublish failed: " << std::hex << hr << "\n";
        return 1;
    }
    hr = LgUiaBridgePublish(nodes, std::size(nodes), 1);
    if (hr != E_INVALIDARG) {
        std::cerr << "stale semantic generation was not rejected\n";
        return 1;
    }

    std::atomic<HRESULT> worker_result = E_PENDING;
    std::thread worker([&]() {
        worker_result = ExerciseProvider(window);
        PostMessageW(window, kWorkerFinished, 0, 0);
    });

    MSG message{};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
        if (message.message == kWorkerFinished) {
            break;
        }
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    worker.join();

    const HRESULT detach_result = LgUiaBridgeDetach();
    DestroyWindow(window);
    UnregisterClassW(kWindowClass, instance);

    if (FAILED(worker_result.load()) || FAILED(detach_result) || state.invoke_count != 1 ||
        state.set_value_count != 1 || state.last_value != L"F:\\exports\\liquigen" ||
        !state.callback_thread_ok.load() || LgUiaBridgeAbiVersion() != LG_UIA_BRIDGE_ABI_VERSION) {
        std::cerr << "semantic provider contract failed: worker=" << std::hex
                  << worker_result.load() << " invoke=" << std::dec << state.invoke_count
                  << " set_value=" << state.set_value_count << "\n";
        return 1;
    }

    std::cout << "semantic provider contract passed\n";
    return 0;
}
