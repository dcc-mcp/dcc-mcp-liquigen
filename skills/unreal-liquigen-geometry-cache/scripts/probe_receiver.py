from dcc_mcp_core.skill import skill_entry, skill_success


@skill_entry
def main():
    import unreal

    required = ("AbcImportSettings", "AlembicImportFactory", "GeometryCacheComponent")
    return skill_success(
        "Geometry Cache receiver capabilities",
        engine_version=unreal.SystemLibrary.get_engine_version(),
        apis={name: hasattr(unreal, name) for name in required},
        scene_changed=False,
    )
