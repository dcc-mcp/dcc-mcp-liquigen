#include "command_set.h"

#include <Windows.h>

#include <cstring>
#include <limits>

namespace liquigen::command_bridge {
namespace {

constexpr std::uintptr_t kExponentMask = 0x3F;
constexpr std::size_t kMaximumCapacity = 4096;

struct CommandSetView {
    OdinString* keys;
    std::uint64_t* values;
    std::uint64_t* controls;
    std::size_t capacity;
};

bool Decode(const CommandSet* set, CommandSetView* view) noexcept {
    if (set == nullptr || view == nullptr || set->encoded_table == 0 || set->count < 0) {
        return false;
    }
    const auto exponent = set->encoded_table & kExponentMask;
    if (exponent >= std::numeric_limits<std::size_t>::digits) {
        return false;
    }
    const auto capacity = std::size_t{1} << exponent;
    if (capacity == 0 || capacity > kMaximumCapacity ||
        static_cast<std::uint64_t>(set->count) > capacity) {
        return false;
    }
    const auto table_base = set->encoded_table & ~kExponentMask;
    if (table_base < 0x10000) {
        return false;
    }
    view->keys = reinterpret_cast<OdinString*>(table_base);
    view->values = reinterpret_cast<std::uint64_t*>(
        table_base + capacity * sizeof(OdinString));
    view->controls = reinterpret_cast<std::uint64_t*>(
        table_base + capacity * (sizeof(OdinString) + sizeof(std::uint64_t)));
    view->capacity = capacity;
    return true;
}

bool Equal(const OdinString& candidate, std::string_view command) noexcept {
    return candidate.size == static_cast<std::int64_t>(command.size()) &&
           candidate.data != nullptr &&
           std::memcmp(candidate.data, command.data(), command.size()) == 0;
}

}  // namespace

std::uint64_t HashCommand(std::uintptr_t table_base, std::string_view command) noexcept {
    std::uint64_t mixed = 0x9E3779B97F4A7C15ULL + table_base;
    mixed = (mixed ^ (mixed >> 30U)) * 0xBF58476D1CE4E5B9ULL;
    mixed = (mixed ^ (mixed >> 27U)) * 0x94D049BB133111EBULL;
    mixed ^= mixed >> 31U;

    std::uint64_t hash = 0xCBF29CE484222325ULL + mixed;
    for (const auto value : command) {
        hash ^= static_cast<unsigned char>(value);
        hash *= 0x100000001B3ULL;
    }
    hash &= 0x7FFFFFFFFFFFFFFFULL;
    return hash == 0 ? 1 : hash;
}

bool ContainsCommand(const CommandSet* set, std::string_view command) noexcept {
    CommandSetView view{};
    if (!Decode(set, &view) || command.empty()) {
        return false;
    }
    const auto table_base = set->encoded_table & ~kExponentMask;
    const auto hash = HashCommand(table_base, command);
    const auto mask = view.capacity - 1;
    auto index = static_cast<std::size_t>(hash) & mask;
    for (std::size_t probes = 0; probes < view.capacity; ++probes) {
        const auto control = view.controls[index];
        if (control == 0) {
            return false;
        }
        if (control == hash && Equal(view.keys[index], command)) {
            return true;
        }
        index = (index + 1) & mask;
    }
    return false;
}

bool EraseCommand(CommandSet* set, std::string_view command) noexcept {
    CommandSetView view{};
    if (!Decode(set, &view) || command.empty()) {
        return false;
    }
    const auto table_base = set->encoded_table & ~kExponentMask;
    const auto hash = HashCommand(table_base, command);
    const auto mask = view.capacity - 1;
    auto hole = static_cast<std::size_t>(hash) & mask;
    for (std::size_t probes = 0; probes < view.capacity; ++probes) {
        const auto control = view.controls[hole];
        if (control == 0) {
            return false;
        }
        if (control == hash && Equal(view.keys[hole], command)) {
            break;
        }
        hole = (hole + 1) & mask;
    }
    if (view.controls[hole] == 0) {
        return false;
    }

    auto next = (hole + 1) & mask;
    while (view.controls[next] != 0) {
        const auto ideal = static_cast<std::size_t>(view.controls[next]) & mask;
        const auto distance_from_ideal = (next - ideal) & mask;
        const auto distance_to_hole = (next - hole) & mask;
        if (distance_from_ideal >= distance_to_hole) {
            view.keys[hole] = view.keys[next];
            view.values[hole] = view.values[next];
            view.controls[hole] = view.controls[next];
            hole = next;
        }
        next = (next + 1) & mask;
    }
    view.keys[hole] = {};
    view.values[hole] = 0;
    MemoryBarrier();
    InterlockedExchange64(
        reinterpret_cast<volatile LONG64*>(&view.controls[hole]), 0);
    InterlockedDecrement64(reinterpret_cast<volatile LONG64*>(&set->count));
    return true;
}

InsertResult InsertCommand(
    CommandSet* set,
    const char* stable_command_data,
    std::size_t command_size) noexcept {
    if (stable_command_data == nullptr || command_size == 0 || command_size > 256) {
        return InsertResult::kInvalid;
    }
    CommandSetView view{};
    if (!Decode(set, &view)) {
        return InsertResult::kUnavailable;
    }
    const std::string_view command(stable_command_data, command_size);
    const auto table_base = set->encoded_table & ~kExponentMask;
    const auto hash = HashCommand(table_base, command);
    const auto mask = view.capacity - 1;
    auto index = static_cast<std::size_t>(hash) & mask;
    for (std::size_t probes = 0; probes < view.capacity; ++probes) {
        const auto control = view.controls[index];
        if (control == hash && Equal(view.keys[index], command)) {
            return InsertResult::kAlreadyPresent;
        }
        if (control == 0) {
            if (set->count >= static_cast<std::int64_t>(view.capacity - 1)) {
                return InsertResult::kFull;
            }
            view.keys[index] = {
                stable_command_data,
                static_cast<std::int64_t>(command_size),
            };
            view.values[index] = 0;
            MemoryBarrier();
            InterlockedExchange64(
                reinterpret_cast<volatile LONG64*>(&view.controls[index]),
                static_cast<LONG64>(hash));
            InterlockedIncrement64(reinterpret_cast<volatile LONG64*>(&set->count));
            return InsertResult::kInserted;
        }
        index = (index + 1) & mask;
    }
    return InsertResult::kFull;
}

}  // namespace liquigen::command_bridge
