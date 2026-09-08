import hashlib
import math
import re
import time
from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_success


def _vector(values, name, nonzero=False):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError(name + " requires three finite numbers")
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(name + " requires three finite numbers")
        value = float(value)
        if not math.isfinite(value) or (nonzero and value == 0):
            raise ValueError(name + " contains invalid values")
        result.append(value)
    return result


@skill_entry
def main(source, destination, asset_name, scale, rotation, import_velocities=False):
    import unreal

    raw = Path(source)
    if not raw.is_absolute() or raw.is_symlink():
        raise ValueError("source must be an absolute regular Alembic file")
    path = raw.resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".abc":
        raise ValueError("source must be an Alembic file")
    with path.open("rb") as stream:
        if stream.read(5) != b"Ogawa":
            raise ValueError("expected an Ogawa Alembic archive")
    if not re.fullmatch(r"/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*", destination):
        raise ValueError("destination must be a /Game asset folder")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", asset_name):
        raise ValueError("asset_name must be an Unreal asset identifier")
    scale = _vector(scale, "scale", True)
    rotation = _vector(rotation, "rotation")
    if not isinstance(import_velocities, bool):
        raise ValueError("import_velocities must be boolean")
    library = unreal.EditorAssetLibrary
    if library.does_directory_exist(destination):
        raise ValueError("destination must be a new asset folder")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    settings = unreal.AbcImportSettings()
    settings.import_type = unreal.AlembicImportType.GEOMETRY_CACHE
    conversion = settings.conversion_settings
    conversion.preset = unreal.AbcConversionPreset.CUSTOM
    conversion.scale = unreal.Vector(*scale)
    conversion.rotation = unreal.Vector(*rotation)
    conversion.flip_u = False
    conversion.flip_v = False
    settings.conversion_settings = conversion
    sampling = settings.sampling_settings
    sampling.sampling_type = unreal.AlembicSamplingType.PER_FRAME
    sampling.frame_steps = 1
    sampling.skip_empty = False
    settings.sampling_settings = sampling
    geometry = settings.geometry_cache_settings
    geometry.apply_constant_topology_optimizations = False
    geometry.motion_vectors = (
        unreal.AbcGeometryCacheMotionVectorsImport.IMPORT_ABC_VELOCITIES_AS_MOTION_VECTORS
        if import_velocities
        else unreal.AbcGeometryCacheMotionVectorsImport.NO_MOTION_VECTORS
    )
    settings.geometry_cache_settings = geometry
    task = unreal.AssetImportTask()
    task.filename = str(path)
    task.destination_path = destination
    task.destination_name = asset_name
    task.automated = True
    task.replace_existing = False
    task.save = True
    task.factory = unreal.AlembicImportFactory()
    task.options = settings
    started = time.monotonic()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    # Unreal can report the same asset path more than once for one import.
    imported = list(dict.fromkeys(task.imported_object_paths))
    if len(imported) != 1:
        raise RuntimeError("expected one Geometry Cache asset; got " + repr(imported))
    asset = library.load_asset(imported[0])
    if not isinstance(asset, unreal.GeometryCache):
        raise RuntimeError("import did not produce a Geometry Cache")
    component = unreal.new_object(unreal.GeometryCacheComponent)
    component.set_geometry_cache(asset)
    duration = component.get_duration()
    frames = component.get_number_of_frames()
    if frames < 2 or duration <= 0:
        raise RuntimeError("imported cache has no animated sample range")
    return skill_success(
        "Alembic imported; visual comparison still required",
        asset_path=asset.get_path_name(),
        source_sha256=digest.hexdigest(),
        source_bytes=path.stat().st_size,
        import_seconds=round(time.monotonic() - started, 3),
        frame_count=frames,
        duration_seconds=duration,
        track_count=component.get_number_of_tracks(),
        scale=scale,
        rotation=rotation,
        import_velocities=import_velocities,
        scene_changed=False,
        visual_acceptance=False,
    )
