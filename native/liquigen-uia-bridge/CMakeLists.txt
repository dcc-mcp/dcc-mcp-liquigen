cmake_minimum_required(VERSION 3.24)

project(liquigen_uia_bridge LANGUAGES CXX)

add_library(liquigen_uia_bridge SHARED
    src/bridge.cpp
)

target_compile_features(liquigen_uia_bridge PRIVATE cxx_std_20)
target_compile_definitions(liquigen_uia_bridge PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    LG_UIA_BRIDGE_BUILD
)
target_include_directories(liquigen_uia_bridge PUBLIC include)
target_link_libraries(liquigen_uia_bridge PRIVATE
    comctl32
    ole32
    oleaut32
    uiautomationcore
)

if(MSVC)
    target_compile_options(liquigen_uia_bridge PRIVATE /W4 /WX /permissive- /EHsc)
endif()

enable_testing()

add_executable(liquigen_uia_bridge_test
    tests/bridge_test.cpp
)
target_compile_features(liquigen_uia_bridge_test PRIVATE cxx_std_20)
target_compile_definitions(liquigen_uia_bridge_test PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_link_libraries(liquigen_uia_bridge_test PRIVATE
    liquigen_uia_bridge
    ole32
    oleaut32
    uiautomationcore
)

if(MSVC)
    target_compile_options(liquigen_uia_bridge_test PRIVATE /W4 /WX /permissive- /EHsc)
endif()

add_test(NAME liquigen_uia_bridge_contract COMMAND liquigen_uia_bridge_test)
