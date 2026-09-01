#include "liquigen_uia_bridge.h"

#include <CommCtrl.h>
#include <OleAuto.h>
#include <UIAutomation.h>
#include <UIAutomationCoreApi.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cwchar>
#include <limits>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

constexpr std::size_t kMaxNodes = 4096;
constexpr std::size_t kMaxIdentityCharacters = 512;
constexpr std::size_t kMaxValueCharacters = 4096;
constexpr UINT kActionMessage = WM_APP + 0x4C47;
constexpr UINT_PTR kSubclassId = 0x4C475549;
constexpr DWORD kActionTimeoutMs = 2000;
constexpr std::uint32_t kKnownFlags = LG_UIA_NODE_ENABLED | LG_UIA_NODE_FOCUSABLE |
                                      LG_UIA_NODE_FOCUSED | LG_UIA_NODE_INVOKE |
                                      LG_UIA_NODE_VALUE | LG_UIA_NODE_VALUE_READ_ONLY;

struct Node {
    std::uint64_t id = 0;
    std::uint64_t parent_id = 0;
    LgUiaControlType control_type = LG_UIA_CONTROL_PANE;
    std::uint32_t flags = 0;
    std::wstring automation_id;
    std::wstring name;
    std::wstring value;
    LgUiaRectV1 bounds{};
    std::vector<std::uint64_t> children;
};

struct BridgeState {
    std::mutex mutex;
    HWND window = nullptr;
    DWORD process_id = 0;
    DWORD ui_thread_id = 0;
    LgUiaCallbacksV1 callbacks{};
    std::uint64_t generation = 0;
    std::uint64_t root_id = 0;
    std::unordered_map<std::uint64_t, Node> nodes;
    bool attached = false;
};

BridgeState g_bridge;

enum class ActionKind {
    Invoke,
    SetValue,
    SetFocus,
};

struct PendingAction {
    std::atomic<long> references{1};
    HANDLE completed = nullptr;
    ActionKind kind = ActionKind::Invoke;
    std::uint64_t generation = 0;
    std::uint64_t node_id = 0;
    std::wstring value;
    HRESULT result = E_PENDING;
};

void AddActionReference(PendingAction* action) {
    action->references.fetch_add(1, std::memory_order_relaxed);
}

void ReleaseAction(PendingAction* action) {
    if (action->references.fetch_sub(1, std::memory_order_acq_rel) == 1) {
        if (action->completed != nullptr) {
            CloseHandle(action->completed);
        }
        delete action;
    }
}

bool IsKnownControlType(LgUiaControlType control_type) {
    switch (control_type) {
        case LG_UIA_CONTROL_PANE:
        case LG_UIA_CONTROL_TAB:
        case LG_UIA_CONTROL_TAB_ITEM:
        case LG_UIA_CONTROL_BUTTON:
        case LG_UIA_CONTROL_EDIT:
        case LG_UIA_CONTROL_TREE:
        case LG_UIA_CONTROL_TREE_ITEM:
        case LG_UIA_CONTROL_PROGRESS:
            return true;
        default:
            return false;
    }
}

CONTROLTYPEID ToUiaControlType(LgUiaControlType control_type) {
    switch (control_type) {
        case LG_UIA_CONTROL_TAB:
            return UIA_TabControlTypeId;
        case LG_UIA_CONTROL_TAB_ITEM:
            return UIA_TabItemControlTypeId;
        case LG_UIA_CONTROL_BUTTON:
            return UIA_ButtonControlTypeId;
        case LG_UIA_CONTROL_EDIT:
            return UIA_EditControlTypeId;
        case LG_UIA_CONTROL_TREE:
            return UIA_TreeControlTypeId;
        case LG_UIA_CONTROL_TREE_ITEM:
            return UIA_TreeItemControlTypeId;
        case LG_UIA_CONTROL_PROGRESS:
            return UIA_ProgressBarControlTypeId;
        case LG_UIA_CONTROL_PANE:
        default:
            return UIA_PaneControlTypeId;
    }
}

HRESULT CopyBoundedString(
    const wchar_t* source, std::size_t maximum, bool allow_empty, std::wstring* output) {
    if (source == nullptr || output == nullptr) {
        return E_INVALIDARG;
    }
    const std::size_t length = wcsnlen_s(source, maximum + 1);
    if (length > maximum || (!allow_empty && length == 0)) {
        return E_INVALIDARG;
    }
    output->assign(source, length);
    return S_OK;
}

bool SnapshotNode(std::uint64_t id, std::uint64_t generation, Node* output) {
    std::scoped_lock lock(g_bridge.mutex);
    if (!g_bridge.attached || generation != g_bridge.generation) {
        return false;
    }
    const auto found = g_bridge.nodes.find(id);
    if (found == g_bridge.nodes.end()) {
        return false;
    }
    *output = found->second;
    return true;
}

bool SnapshotRoot(std::uint64_t generation, std::uint64_t* root_id) {
    std::scoped_lock lock(g_bridge.mutex);
    if (!g_bridge.attached || generation != g_bridge.generation || g_bridge.root_id == 0) {
        return false;
    }
    *root_id = g_bridge.root_id;
    return true;
}

HRESULT ExecuteAction(PendingAction* action) {
    LgUiaCallbacksV1 callbacks{};
    Node node;
    {
        std::scoped_lock lock(g_bridge.mutex);
        if (!g_bridge.attached || action->generation != g_bridge.generation) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        const auto found = g_bridge.nodes.find(action->node_id);
        if (found == g_bridge.nodes.end()) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        node = found->second;
        callbacks = g_bridge.callbacks;
    }
    if ((node.flags & LG_UIA_NODE_ENABLED) == 0) {
        return UIA_E_ELEMENTNOTENABLED;
    }
    switch (action->kind) {
        case ActionKind::Invoke:
            if ((node.flags & LG_UIA_NODE_INVOKE) == 0 || callbacks.invoke == nullptr) {
                return UIA_E_NOTSUPPORTED;
            }
            return callbacks.invoke(callbacks.context, action->node_id);
        case ActionKind::SetValue:
            if ((node.flags & LG_UIA_NODE_VALUE) == 0 ||
                (node.flags & LG_UIA_NODE_VALUE_READ_ONLY) != 0 || callbacks.set_value == nullptr) {
                return UIA_E_NOTSUPPORTED;
            }
            return callbacks.set_value(callbacks.context, action->node_id, action->value.c_str());
        case ActionKind::SetFocus:
            if ((node.flags & LG_UIA_NODE_FOCUSABLE) == 0 || callbacks.set_focus == nullptr) {
                return UIA_E_NOTSUPPORTED;
            }
            return callbacks.set_focus(callbacks.context, action->node_id);
        default:
            return E_UNEXPECTED;
    }
}

HRESULT DispatchAction(
    ActionKind kind,
    std::uint64_t generation,
    std::uint64_t node_id,
    const wchar_t* value = L"") {
    HWND window = nullptr;
    DWORD ui_thread_id = 0;
    {
        std::scoped_lock lock(g_bridge.mutex);
        if (!g_bridge.attached || generation != g_bridge.generation) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        window = g_bridge.window;
        ui_thread_id = g_bridge.ui_thread_id;
    }

    PendingAction direct;
    direct.kind = kind;
    direct.generation = generation;
    direct.node_id = node_id;
    direct.value = value == nullptr ? L"" : value;
    if (GetCurrentThreadId() == ui_thread_id) {
        return ExecuteAction(&direct);
    }

    auto* pending = new (std::nothrow) PendingAction();
    if (pending == nullptr) {
        return E_OUTOFMEMORY;
    }
    pending->completed = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (pending->completed == nullptr) {
        delete pending;
        return HRESULT_FROM_WIN32(GetLastError());
    }
    pending->kind = kind;
    pending->generation = generation;
    pending->node_id = node_id;
    pending->value = value == nullptr ? L"" : value;

    AddActionReference(pending);
    if (!PostMessageW(window, kActionMessage, 0, reinterpret_cast<LPARAM>(pending))) {
        const HRESULT error = HRESULT_FROM_WIN32(GetLastError());
        ReleaseAction(pending);
        ReleaseAction(pending);
        return error;
    }

    const DWORD wait_result = WaitForSingleObject(pending->completed, kActionTimeoutMs);
    HRESULT result = HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    if (wait_result == WAIT_OBJECT_0) {
        result = pending->result;
    } else if (wait_result == WAIT_FAILED) {
        result = HRESULT_FROM_WIN32(GetLastError());
    }
    ReleaseAction(pending);
    return result;
}

class Provider final : public IRawElementProviderSimple,
                       public IRawElementProviderFragment,
                       public IRawElementProviderFragmentRoot,
                       public IInvokeProvider,
                       public IValueProvider {
  public:
    Provider(std::uint64_t id, std::uint64_t generation)
        : id_(id), generation_(generation) {}

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID interface_id, void** object) override {
        if (object == nullptr) {
            return E_INVALIDARG;
        }
        *object = nullptr;
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        std::uint64_t root_id = 0;
        if (!SnapshotRoot(generation_, &root_id)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }

        if (interface_id == __uuidof(IUnknown) ||
            interface_id == __uuidof(IRawElementProviderSimple)) {
            *object = static_cast<IRawElementProviderSimple*>(this);
        } else if (interface_id == __uuidof(IRawElementProviderFragment)) {
            *object = static_cast<IRawElementProviderFragment*>(this);
        } else if (interface_id == __uuidof(IRawElementProviderFragmentRoot) && id_ == root_id) {
            *object = static_cast<IRawElementProviderFragmentRoot*>(this);
        } else if (interface_id == __uuidof(IInvokeProvider) &&
                   (node.flags & LG_UIA_NODE_INVOKE) != 0) {
            *object = static_cast<IInvokeProvider*>(this);
        } else if (interface_id == __uuidof(IValueProvider) &&
                   (node.flags & LG_UIA_NODE_VALUE) != 0) {
            *object = static_cast<IValueProvider*>(this);
        } else {
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }

    ULONG STDMETHODCALLTYPE AddRef() override {
        return references_.fetch_add(1, std::memory_order_relaxed) + 1;
    }

    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = references_.fetch_sub(1, std::memory_order_acq_rel) - 1;
        if (remaining == 0) {
            delete this;
        }
        return remaining;
    }

    HRESULT STDMETHODCALLTYPE get_ProviderOptions(ProviderOptions* options) override {
        if (options == nullptr) {
            return E_INVALIDARG;
        }
        *options = ProviderOptions_ServerSideProvider | ProviderOptions_UseComThreading;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE GetPatternProvider(PATTERNID pattern_id, IUnknown** provider) override {
        if (provider == nullptr) {
            return E_INVALIDARG;
        }
        *provider = nullptr;
        if (pattern_id == UIA_InvokePatternId) {
            return QueryInterface(__uuidof(IInvokeProvider), reinterpret_cast<void**>(provider));
        }
        if (pattern_id == UIA_ValuePatternId) {
            return QueryInterface(__uuidof(IValueProvider), reinterpret_cast<void**>(provider));
        }
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE GetPropertyValue(PROPERTYID property_id, VARIANT* value) override {
        if (value == nullptr) {
            return E_INVALIDARG;
        }
        VariantInit(value);
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        std::uint64_t root_id = 0;
        if (!SnapshotRoot(generation_, &root_id)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }

        switch (property_id) {
            case UIA_ControlTypePropertyId:
                value->vt = VT_I4;
                value->lVal = ToUiaControlType(node.control_type);
                return S_OK;
            case UIA_NamePropertyId:
                return SetBstr(node.name, value);
            case UIA_AutomationIdPropertyId:
                return SetBstr(node.automation_id, value);
            case UIA_FrameworkIdPropertyId:
                return SetBstr(L"LiquiGen", value);
            case UIA_IsControlElementPropertyId:
            case UIA_IsContentElementPropertyId:
                value->vt = VT_BOOL;
                value->boolVal = VARIANT_TRUE;
                return S_OK;
            case UIA_IsEnabledPropertyId:
                value->vt = VT_BOOL;
                value->boolVal =
                    (node.flags & LG_UIA_NODE_ENABLED) != 0 ? VARIANT_TRUE : VARIANT_FALSE;
                return S_OK;
            case UIA_IsKeyboardFocusablePropertyId:
                value->vt = VT_BOOL;
                value->boolVal =
                    (node.flags & LG_UIA_NODE_FOCUSABLE) != 0 ? VARIANT_TRUE : VARIANT_FALSE;
                return S_OK;
            case UIA_HasKeyboardFocusPropertyId:
                value->vt = VT_BOOL;
                value->boolVal =
                    (node.flags & LG_UIA_NODE_FOCUSED) != 0 ? VARIANT_TRUE : VARIANT_FALSE;
                return S_OK;
            case UIA_NativeWindowHandlePropertyId:
                if (id_ == root_id) {
                    std::scoped_lock lock(g_bridge.mutex);
                    value->vt = VT_I4;
                    value->lVal = static_cast<LONG>(reinterpret_cast<INT_PTR>(g_bridge.window));
                }
                return S_OK;
            default:
                return S_OK;
        }
    }

    HRESULT STDMETHODCALLTYPE get_HostRawElementProvider(
        IRawElementProviderSimple** provider) override {
        if (provider == nullptr) {
            return E_INVALIDARG;
        }
        *provider = nullptr;
        std::uint64_t root_id = 0;
        if (!SnapshotRoot(generation_, &root_id)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        if (id_ != root_id) {
            return S_OK;
        }
        HWND window = nullptr;
        {
            std::scoped_lock lock(g_bridge.mutex);
            window = g_bridge.window;
        }
        return UiaHostProviderFromHwnd(window, provider);
    }

    HRESULT STDMETHODCALLTYPE Navigate(
        NavigateDirection direction, IRawElementProviderFragment** provider) override {
        if (provider == nullptr) {
            return E_INVALIDARG;
        }
        *provider = nullptr;
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }

        std::uint64_t target_id = 0;
        if (direction == NavigateDirection_Parent) {
            target_id = node.parent_id;
        } else if (direction == NavigateDirection_FirstChild && !node.children.empty()) {
            target_id = node.children.front();
        } else if (direction == NavigateDirection_LastChild && !node.children.empty()) {
            target_id = node.children.back();
        } else if ((direction == NavigateDirection_NextSibling ||
                    direction == NavigateDirection_PreviousSibling) &&
                   node.parent_id != 0) {
            Node parent;
            if (!SnapshotNode(node.parent_id, generation_, &parent)) {
                return UIA_E_ELEMENTNOTAVAILABLE;
            }
            const auto current = std::find(parent.children.begin(), parent.children.end(), id_);
            if (current != parent.children.end()) {
                if (direction == NavigateDirection_NextSibling &&
                    std::next(current) != parent.children.end()) {
                    target_id = *std::next(current);
                } else if (direction == NavigateDirection_PreviousSibling &&
                           current != parent.children.begin()) {
                    target_id = *std::prev(current);
                }
            }
        }
        if (target_id == 0) {
            return S_OK;
        }
        *provider = MakeProvider(target_id);
        return *provider == nullptr ? E_OUTOFMEMORY : S_OK;
    }

    HRESULT STDMETHODCALLTYPE GetRuntimeId(SAFEARRAY** runtime_id) override {
        if (runtime_id == nullptr) {
            return E_INVALIDARG;
        }
        *runtime_id = nullptr;
        std::uint64_t root_id = 0;
        if (!SnapshotRoot(generation_, &root_id)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        if (id_ == root_id) {
            return S_OK;
        }
        SAFEARRAY* array = SafeArrayCreateVector(VT_I4, 0, 5);
        if (array == nullptr) {
            return E_OUTOFMEMORY;
        }
        LONG* values = nullptr;
        HRESULT hr = SafeArrayAccessData(array, reinterpret_cast<void**>(&values));
        if (FAILED(hr)) {
            SafeArrayDestroy(array);
            return hr;
        }
        values[0] = UiaAppendRuntimeId;
        values[1] = static_cast<LONG>(generation_ & 0xffffffffu);
        values[2] = static_cast<LONG>((generation_ >> 32u) & 0xffffffffu);
        values[3] = static_cast<LONG>(id_ & 0xffffffffu);
        values[4] = static_cast<LONG>((id_ >> 32u) & 0xffffffffu);
        SafeArrayUnaccessData(array);
        *runtime_id = array;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE get_BoundingRectangle(UiaRect* rectangle) override {
        if (rectangle == nullptr) {
            return E_INVALIDARG;
        }
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        rectangle->left = node.bounds.left;
        rectangle->top = node.bounds.top;
        rectangle->width = node.bounds.width;
        rectangle->height = node.bounds.height;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE GetEmbeddedFragmentRoots(SAFEARRAY** roots) override {
        if (roots == nullptr) {
            return E_INVALIDARG;
        }
        *roots = nullptr;
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE SetFocus() override {
        return DispatchAction(ActionKind::SetFocus, generation_, id_);
    }

    HRESULT STDMETHODCALLTYPE get_FragmentRoot(
        IRawElementProviderFragmentRoot** root) override {
        if (root == nullptr) {
            return E_INVALIDARG;
        }
        *root = nullptr;
        std::uint64_t root_id = 0;
        if (!SnapshotRoot(generation_, &root_id)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        auto* provider = new (std::nothrow) Provider(root_id, generation_);
        if (provider == nullptr) {
            return E_OUTOFMEMORY;
        }
        *root = static_cast<IRawElementProviderFragmentRoot*>(provider);
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE ElementProviderFromPoint(
        double x, double y, IRawElementProviderFragment** provider) override {
        if (provider == nullptr) {
            return E_INVALIDARG;
        }
        *provider = nullptr;
        std::uint64_t match = 0;
        std::size_t match_depth = 0;
        {
            std::scoped_lock lock(g_bridge.mutex);
            if (!g_bridge.attached || generation_ != g_bridge.generation) {
                return UIA_E_ELEMENTNOTAVAILABLE;
            }
            for (const auto& [candidate_id, candidate] : g_bridge.nodes) {
                const auto& bounds = candidate.bounds;
                if (x < bounds.left || y < bounds.top || x > bounds.left + bounds.width ||
                    y > bounds.top + bounds.height) {
                    continue;
                }
                std::size_t depth = 0;
                std::uint64_t parent_id = candidate.parent_id;
                while (parent_id != 0 && depth <= g_bridge.nodes.size()) {
                    const auto parent = g_bridge.nodes.find(parent_id);
                    if (parent == g_bridge.nodes.end()) {
                        break;
                    }
                    ++depth;
                    parent_id = parent->second.parent_id;
                }
                if (match == 0 || depth >= match_depth) {
                    match = candidate_id;
                    match_depth = depth;
                }
            }
        }
        if (match == 0) {
            return S_OK;
        }
        *provider = MakeProvider(match);
        return *provider == nullptr ? E_OUTOFMEMORY : S_OK;
    }

    HRESULT STDMETHODCALLTYPE GetFocus(IRawElementProviderFragment** provider) override {
        if (provider == nullptr) {
            return E_INVALIDARG;
        }
        *provider = nullptr;
        std::uint64_t focused_id = 0;
        {
            std::scoped_lock lock(g_bridge.mutex);
            if (!g_bridge.attached || generation_ != g_bridge.generation) {
                return UIA_E_ELEMENTNOTAVAILABLE;
            }
            for (const auto& [candidate_id, candidate] : g_bridge.nodes) {
                if ((candidate.flags & LG_UIA_NODE_FOCUSED) != 0) {
                    focused_id = candidate_id;
                    break;
                }
            }
        }
        if (focused_id == 0) {
            return S_OK;
        }
        *provider = MakeProvider(focused_id);
        return *provider == nullptr ? E_OUTOFMEMORY : S_OK;
    }

    HRESULT STDMETHODCALLTYPE Invoke() override {
        return DispatchAction(ActionKind::Invoke, generation_, id_);
    }

    HRESULT STDMETHODCALLTYPE SetValue(LPCWSTR value) override {
        if (value == nullptr || wcsnlen_s(value, kMaxValueCharacters + 1) > kMaxValueCharacters) {
            return E_INVALIDARG;
        }
        return DispatchAction(ActionKind::SetValue, generation_, id_, value);
    }

    HRESULT STDMETHODCALLTYPE get_Value(BSTR* value) override {
        if (value == nullptr) {
            return E_INVALIDARG;
        }
        *value = nullptr;
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        *value = SysAllocStringLen(node.value.data(), static_cast<UINT>(node.value.size()));
        return *value == nullptr && !node.value.empty() ? E_OUTOFMEMORY : S_OK;
    }

    HRESULT STDMETHODCALLTYPE get_IsReadOnly(BOOL* read_only) override {
        if (read_only == nullptr) {
            return E_INVALIDARG;
        }
        Node node;
        if (!SnapshotNode(id_, generation_, &node)) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        *read_only = (node.flags & LG_UIA_NODE_VALUE_READ_ONLY) != 0 ? TRUE : FALSE;
        return S_OK;
    }

  private:
    ~Provider() = default;

    static HRESULT SetBstr(const std::wstring& text, VARIANT* value) {
        value->vt = VT_BSTR;
        value->bstrVal = SysAllocStringLen(text.data(), static_cast<UINT>(text.size()));
        return value->bstrVal == nullptr && !text.empty() ? E_OUTOFMEMORY : S_OK;
    }

    IRawElementProviderFragment* MakeProvider(std::uint64_t id) const {
        auto* provider = new (std::nothrow) Provider(id, generation_);
        return provider == nullptr
                   ? nullptr
                   : static_cast<IRawElementProviderFragment*>(provider);
    }

    std::atomic<ULONG> references_{1};
    const std::uint64_t id_;
    const std::uint64_t generation_;
};

bool ContainsCycle(
    std::uint64_t node_id,
    const std::unordered_map<std::uint64_t, Node>& nodes,
    std::unordered_set<std::uint64_t>* visiting,
    std::unordered_set<std::uint64_t>* visited) {
    if (visited->contains(node_id)) {
        return false;
    }
    if (!visiting->insert(node_id).second) {
        return true;
    }
    const auto node = nodes.find(node_id);
    if (node == nodes.end()) {
        return true;
    }
    for (const std::uint64_t child_id : node->second.children) {
        if (ContainsCycle(child_id, nodes, visiting, visited)) {
            return true;
        }
    }
    visiting->erase(node_id);
    visited->insert(node_id);
    return false;
}

LRESULT CALLBACK BridgeSubclassProc(
    HWND window,
    UINT message,
    WPARAM wparam,
    LPARAM lparam,
    UINT_PTR,
    DWORD_PTR) {
    if (message == WM_GETOBJECT && static_cast<LONG>(lparam) == UiaRootObjectId) {
        std::uint64_t root_id = 0;
        std::uint64_t generation = 0;
        {
            std::scoped_lock lock(g_bridge.mutex);
            if (!g_bridge.attached || g_bridge.window != window || g_bridge.root_id == 0) {
                return DefSubclassProc(window, message, wparam, lparam);
            }
            root_id = g_bridge.root_id;
            generation = g_bridge.generation;
        }
        auto* provider = new (std::nothrow) Provider(root_id, generation);
        if (provider == nullptr) {
            return 0;
        }
        const LRESULT result = UiaReturnRawElementProvider(
            window, wparam, lparam, static_cast<IRawElementProviderSimple*>(provider));
        provider->Release();
        return result;
    }
    if (message == kActionMessage) {
        auto* action = reinterpret_cast<PendingAction*>(lparam);
        if (action != nullptr) {
            action->result = ExecuteAction(action);
            SetEvent(action->completed);
            ReleaseAction(action);
        }
        return 0;
    }
    if (message == WM_NCDESTROY) {
        UiaReturnRawElementProvider(window, 0, 0, nullptr);
        std::scoped_lock lock(g_bridge.mutex);
        if (g_bridge.window == window) {
            g_bridge.window = nullptr;
            g_bridge.process_id = 0;
            g_bridge.ui_thread_id = 0;
            g_bridge.callbacks = {};
            g_bridge.generation = 0;
            g_bridge.root_id = 0;
            g_bridge.nodes.clear();
            g_bridge.attached = false;
        }
    }
    return DefSubclassProc(window, message, wparam, lparam);
}

}  // namespace

std::uint32_t WINAPI LgUiaBridgeAbiVersion() {
    return LG_UIA_BRIDGE_ABI_VERSION;
}

HRESULT WINAPI LgUiaBridgeAttach(HWND window, const LgUiaCallbacksV1* callbacks) {
    if (window == nullptr || callbacks == nullptr ||
        callbacks->struct_size < sizeof(LgUiaCallbacksV1) || !IsWindow(window)) {
        return E_INVALIDARG;
    }
    DWORD process_id = 0;
    const DWORD thread_id = GetWindowThreadProcessId(window, &process_id);
    if (thread_id == 0 || process_id != GetCurrentProcessId()) {
        return HRESULT_FROM_WIN32(ERROR_ACCESS_DENIED);
    }
    if (thread_id != GetCurrentThreadId()) {
        return HRESULT_FROM_WIN32(ERROR_INVALID_THREAD_ID);
    }

    {
        std::scoped_lock lock(g_bridge.mutex);
        if (g_bridge.attached) {
            return HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS);
        }
    }
    if (!SetWindowSubclass(window, BridgeSubclassProc, kSubclassId, 0)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    {
        std::scoped_lock lock(g_bridge.mutex);
        g_bridge.window = window;
        g_bridge.process_id = process_id;
        g_bridge.ui_thread_id = thread_id;
        g_bridge.callbacks = *callbacks;
        g_bridge.generation = 0;
        g_bridge.root_id = 0;
        g_bridge.nodes.clear();
        g_bridge.attached = true;
    }
    return S_OK;
}

HRESULT WINAPI LgUiaBridgePublish(
    const LgUiaNodeV1* nodes, std::size_t node_count, std::uint64_t generation) {
    if (nodes == nullptr || node_count == 0 || node_count > kMaxNodes || generation == 0) {
        return E_INVALIDARG;
    }

    LgUiaCallbacksV1 callbacks{};
    std::uint64_t current_generation = 0;
    {
        std::scoped_lock lock(g_bridge.mutex);
        if (!g_bridge.attached) {
            return CO_E_NOTINITIALIZED;
        }
        callbacks = g_bridge.callbacks;
        current_generation = g_bridge.generation;
    }
    if (generation <= current_generation) {
        return E_INVALIDARG;
    }

    std::unordered_map<std::uint64_t, Node> candidate;
    candidate.reserve(node_count);
    std::unordered_set<std::wstring> automation_ids;
    std::uint64_t root_id = 0;

    for (std::size_t index = 0; index < node_count; ++index) {
        const LgUiaNodeV1& source = nodes[index];
        if (source.struct_size < sizeof(LgUiaNodeV1) || source.id == 0 ||
            !IsKnownControlType(source.control_type) || (source.flags & ~kKnownFlags) != 0 ||
            !std::isfinite(source.bounds.left) || !std::isfinite(source.bounds.top) ||
            !std::isfinite(source.bounds.width) || !std::isfinite(source.bounds.height) ||
            source.bounds.width < 0 || source.bounds.height < 0) {
            return E_INVALIDARG;
        }
        if ((source.flags & LG_UIA_NODE_INVOKE) != 0 && callbacks.invoke == nullptr) {
            return E_INVALIDARG;
        }
        if ((source.flags & LG_UIA_NODE_VALUE) != 0 &&
            (source.flags & LG_UIA_NODE_VALUE_READ_ONLY) == 0 && callbacks.set_value == nullptr) {
            return E_INVALIDARG;
        }
        if ((source.flags & LG_UIA_NODE_FOCUSABLE) != 0 && callbacks.set_focus == nullptr) {
            return E_INVALIDARG;
        }

        Node node;
        node.id = source.id;
        node.parent_id = source.parent_id;
        node.control_type = source.control_type;
        node.flags = source.flags;
        node.bounds = source.bounds;
        HRESULT hr = CopyBoundedString(
            source.automation_id, kMaxIdentityCharacters, false, &node.automation_id);
        if (SUCCEEDED(hr)) {
            hr = CopyBoundedString(source.name, kMaxIdentityCharacters, true, &node.name);
        }
        if (SUCCEEDED(hr)) {
            hr = CopyBoundedString(source.value, kMaxValueCharacters, true, &node.value);
        }
        if (FAILED(hr) || !automation_ids.insert(node.automation_id).second ||
            !candidate.emplace(node.id, std::move(node)).second) {
            return E_INVALIDARG;
        }
        if (source.parent_id == 0) {
            if (root_id != 0) {
                return E_INVALIDARG;
            }
            root_id = source.id;
        }
    }
    if (root_id == 0) {
        return E_INVALIDARG;
    }
    for (auto& [node_id, node] : candidate) {
        if (node.parent_id == 0) {
            continue;
        }
        const auto parent = candidate.find(node.parent_id);
        if (parent == candidate.end() || node.parent_id == node_id) {
            return E_INVALIDARG;
        }
        parent->second.children.push_back(node_id);
    }
    std::unordered_set<std::uint64_t> visiting;
    std::unordered_set<std::uint64_t> visited;
    if (ContainsCycle(root_id, candidate, &visiting, &visited) || visited.size() != node_count) {
        return E_INVALIDARG;
    }

    {
        std::scoped_lock lock(g_bridge.mutex);
        if (!g_bridge.attached || generation <= g_bridge.generation) {
            return UIA_E_ELEMENTNOTAVAILABLE;
        }
        g_bridge.nodes = std::move(candidate);
        g_bridge.root_id = root_id;
        g_bridge.generation = generation;
    }
    return S_OK;
}

HRESULT WINAPI LgUiaBridgeDetach() {
    HWND window = nullptr;
    DWORD ui_thread_id = 0;
    {
        std::scoped_lock lock(g_bridge.mutex);
        if (!g_bridge.attached) {
            return S_FALSE;
        }
        window = g_bridge.window;
        ui_thread_id = g_bridge.ui_thread_id;
    }
    if (GetCurrentThreadId() != ui_thread_id) {
        return HRESULT_FROM_WIN32(ERROR_INVALID_THREAD_ID);
    }
    UiaReturnRawElementProvider(window, 0, 0, nullptr);
    if (!RemoveWindowSubclass(window, BridgeSubclassProc, kSubclassId)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    {
        std::scoped_lock lock(g_bridge.mutex);
        g_bridge.window = nullptr;
        g_bridge.process_id = 0;
        g_bridge.ui_thread_id = 0;
        g_bridge.callbacks = {};
        g_bridge.generation = 0;
        g_bridge.root_id = 0;
        g_bridge.nodes.clear();
        g_bridge.attached = false;
    }
    return S_OK;
}
