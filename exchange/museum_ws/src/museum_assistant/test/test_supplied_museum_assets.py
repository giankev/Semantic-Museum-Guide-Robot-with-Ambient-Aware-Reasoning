import importlib.util
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ASSET_DIR = PACKAGE_ROOT / "worlds" / "supplied_museum"
FORBIDDEN_PATHS = (
    "file:///Desktop/",
    "/home/kevin/",
    "/root/exchange/",
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def _asset_names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir() if path.is_file()}


def _load_supplied_launch_module():
    launch_path = (
        PACKAGE_ROOT / "launch" / "tiago_supplied_museum_world.launch.py"
    )
    spec = importlib.util.spec_from_file_location(
        "tiago_supplied_museum_world_launch", launch_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_supplied_world_is_valid_portable_sdf():
    world_path = SOURCE_ASSET_DIR / "museum.world"
    world_text = world_path.read_text(encoding="utf-8")
    root = ET.fromstring(world_text)

    assert root.tag == "sdf"
    assert root.attrib["version"] == "1.6"
    assert all(path not in world_text for path in FORBIDDEN_PATHS)
    mesh_uris = [element.text for element in root.findall(".//mesh/uri")]
    assert mesh_uris == ["model.dae", "collision.dae"]
    floor_collision = root.find(
        ".//model[@name='floor']/link/collision"
    )
    collision_surface = floor_collision.find("surface/friction/ode")
    assert floor_collision.find("pose").text == "0 0 -0.011 0 0 0"
    assert collision_surface.find("mu").text == "10.0"
    assert collision_surface.find("mu2").text == "10.0"


def test_supplied_collada_texture_references_are_complete():
    dae_path = SOURCE_ASSET_DIR / "model.dae"
    root = ET.parse(dae_path)
    asset = root.find("c:asset", COLLADA_NS)
    unit = asset.find("c:unit", COLLADA_NS)
    up_axis = asset.find("c:up_axis", COLLADA_NS)
    texture_names = {
        element.text.strip()
        for element in root.findall(
            ".//c:library_images/c:image/c:init_from", COLLADA_NS
        )
    }

    assert len(texture_names) == 29
    assert unit.attrib["meter"] == "1"
    assert up_axis.text == "Y_UP"
    assert all(Path(name).name == name for name in texture_names)
    assert not {
        name for name in texture_names if not (SOURCE_ASSET_DIR / name).is_file()
    }
    assert all(
        Path(name).suffix.lower() in IMAGE_SUFFIXES for name in texture_names
    )


def test_collision_derivative_omits_only_floor_and_evidenced_passage_box():
    visual_root = ET.parse(SOURCE_ASSET_DIR / "model.dae")
    collision_root = ET.parse(SOURCE_ASSET_DIR / "collision.dae")
    geometry_path = ".//c:geometry[@id='Circle_1']/c:mesh"
    visual_mesh = visual_root.find(geometry_path, COLLADA_NS)
    collision_mesh = collision_root.find(geometry_path, COLLADA_NS)
    visual_polylist = visual_mesh.find("c:polylist", COLLADA_NS)
    collision_polylist = collision_mesh.find("c:polylist", COLLADA_NS)
    visual_indices = [
        int(value)
        for value in visual_polylist.find("c:p", COLLADA_NS).text.split()
    ]
    collision_indices = [
        int(value)
        for value in collision_polylist.find("c:p", COLLADA_NS).text.split()
    ]
    removed_polygons = {
        3828: (4803, 4804, 4805),
        3829: (4803, 4805, 4806),
        4160: (5217, 5218, 5219),
        4161: (5217, 5219, 5220),
        4573: (5916, 5917, 5918),
        4574: (5916, 5918, 5919),
        4577: (5922, 5923, 5924),
        4578: (5922, 5924, 5925),
        4579: (5926, 5927, 5928),
        4580: (5926, 5928, 5929),
        4581: (5930, 5931, 5932),
        4582: (5930, 5932, 5933),
    }
    parents = list(range(8822))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first, second):
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    for offset in range(0, len(visual_indices), 3):
        union(visual_indices[offset], visual_indices[offset + 1])
        union(visual_indices[offset], visual_indices[offset + 2])
    components = {}
    for polygon in range(int(visual_polylist.attrib["count"])):
        components.setdefault(find(visual_indices[3 * polygon]), []).append(
            polygon
        )
    floor_components = [
        polygons for polygons in components.values() if len(polygons) == 416
    ]

    assert len(floor_components) == 1
    floor_polygons = set(floor_components[0])
    assert hashlib.sha256(
        " ".join(map(str, sorted(floor_polygons))).encode("ascii")
    ).hexdigest() == (
        "47bdb7aeeb429d2185b4c14676d5b8e819da0425911f413f5b7ddf7faeb2e72c"
    )
    removed_polygon_indexes = floor_polygons | set(removed_polygons)
    expected_indices = [
        value
        for polygon in range(int(visual_polylist.attrib["count"]))
        if polygon not in removed_polygon_indexes
        for value in visual_indices[3 * polygon : 3 * polygon + 3]
    ]

    for polygon, expected in removed_polygons.items():
        assert tuple(visual_indices[3 * polygon : 3 * polygon + 3]) == expected
    assert visual_polylist.attrib["count"] == "7012"
    assert collision_polylist.attrib["count"] == "6584"
    assert collision_indices == expected_indices
    assert all(
        source.find("c:float_array", COLLADA_NS).text
        == collision_mesh.find(
            f"c:source[@id='{source.attrib['id']}']/c:float_array", COLLADA_NS
        ).text
        for source in visual_mesh.findall("c:source", COLLADA_NS)
    )


def test_complete_supplied_asset_tree_is_installed():
    installed_dir = (
        Path(get_package_share_directory("museum_assistant"))
        / "worlds"
        / "supplied_museum"
    )

    assert installed_dir.is_dir()
    assert _asset_names(installed_dir) == _asset_names(SOURCE_ASSET_DIR)
    assert all(path.stat().st_size > 0 for path in installed_dir.iterdir())
    assert (installed_dir / "museum.world").is_file()
    assert (installed_dir / "model.dae").is_file()
    assert (installed_dir / "collision.dae").is_file()


def test_supplied_launch_resolves_the_installed_world():
    module = _load_supplied_launch_module()
    resolved_world = Path(module.supplied_museum_world_path())

    assert resolved_world.is_file()
    assert resolved_world.name == "museum.world"
    assert resolved_world.parent.name == "supplied_museum"
