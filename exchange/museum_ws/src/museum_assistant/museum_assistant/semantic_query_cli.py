import argparse
import json
from pathlib import Path

from museum_assistant.semantic_graph import load_semantic_graph

try:
    from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
except ModuleNotFoundError:
    PackageNotFoundError = RuntimeError
    get_package_share_directory = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the museum semantic map and print a room recommendation as JSON."
    )
    parser.add_argument("--style", help="Artwork style to search for, for example impressionism")
    parser.add_argument(
        "--avoid-crowd",
        action="store_true",
        help="Reject rooms whose crowd level is high",
    )
    parser.add_argument(
        "--child-friendly",
        action="store_true",
        help="Require a child-friendly room",
    )
    parser.add_argument(
        "--wheelchair-accessible",
        action="store_true",
        help="Require a wheelchair-accessible room",
    )
    parser.add_argument("--map", help="Path to a semantic_map.yaml file")
    args = parser.parse_args()

    map_path = args.map or _default_map_path()
    semantic_graph = load_semantic_graph(map_path)
    recommendation = semantic_graph.recommend_room(
        style=args.style,
        avoid_crowd=args.avoid_crowd,
        child_friendly=True if args.child_friendly else None,
        wheelchair_accessible=True if args.wheelchair_accessible else None,
    )
    print(json.dumps(recommendation, indent=2))


def _default_map_path() -> str:
    try:
        if get_package_share_directory is None:
            raise PackageNotFoundError("ament_index_python is not available")
        share_dir = get_package_share_directory("museum_assistant")
        return f"{share_dir}/config/semantic_map.yaml"
    except PackageNotFoundError:
        package_dir = Path(__file__).resolve().parents[1]
        return str(package_dir / "config" / "semantic_map.yaml")


if __name__ == "__main__":
    main()
