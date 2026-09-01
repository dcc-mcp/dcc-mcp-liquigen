#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace liquigen::command_bridge {

struct OdinString {
    const char* data;
    std::int64_t size;
};

struct CommandSet {
    std::uintptr_t encoded_table;
    std::int64_t count;
};

enum class InsertResult {
    kInserted,
    kAlreadyPresent,
    kUnavailable,
    kFull,
    kInvalid,
};

std::uint64_t HashCommand(std::uintptr_t table_base, std::string_view command) noexcept;
InsertResult InsertCommand(
    CommandSet* set,
    const char* stable_command_data,
    std::size_t command_size) noexcept;
bool ContainsCommand(const CommandSet* set, std::string_view command) noexcept;
bool EraseCommand(CommandSet* set, std::string_view command) noexcept;

}  // namespace liquigen::command_bridge
