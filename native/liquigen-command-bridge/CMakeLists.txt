cmake_minimum_required(VERSION 3.24)

project(liquigen_command_bridge LANGUAGES CXX)

add_library(liquigen_command_set STATIC
    src/command_set.cpp
)
target_compile_features(liquigen_command_set PUBLIC cxx_std_20)
target_compile_definitions(liquigen_command_set PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_include_directories(liquigen_command_set PUBLIC include)

add_library(dcc_mcp_liquigen_command_hook SHARED
    src/hook.cpp
)
target_compile_features(dcc_mcp_liquigen_command_hook PRIVATE cxx_std_20)
target_compile_definitions(dcc_mcp_liquigen_command_hook PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_include_directories(dcc_mcp_liquigen_command_hook PRIVATE include)
target_link_libraries(dcc_mcp_liquigen_command_hook PRIVATE liquigen_command_set)

add_executable(dcc_mcp_liquigen_command_client
    src/client.cpp
)
target_compile_features(dcc_mcp_liquigen_command_client PRIVATE cxx_std_20)
target_compile_definitions(dcc_mcp_liquigen_command_client PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_include_directories(dcc_mcp_liquigen_command_client PRIVATE include)

if(MSVC)
    foreach(target
        liquigen_command_set
        dcc_mcp_liquigen_command_hook
        dcc_mcp_liquigen_command_client
    )
        target_compile_options(${target} PRIVATE /W4 /WX /permissive- /EHsc)
    endforeach()
endif()

enable_testing()

add_executable(liquigen_command_set_test
    tests/command_set_test.cpp
)
target_compile_features(liquigen_command_set_test PRIVATE cxx_std_20)
target_compile_definitions(liquigen_command_set_test PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_include_directories(liquigen_command_set_test PRIVATE include)
target_link_libraries(liquigen_command_set_test PRIVATE liquigen_command_set)

if(MSVC)
    target_compile_options(liquigen_command_set_test PRIVATE /W4 /WX /permissive- /EHsc)
endif()

add_test(NAME liquigen_command_set_contract COMMAND liquigen_command_set_test)
