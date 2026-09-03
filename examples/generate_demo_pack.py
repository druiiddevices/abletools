from pathlib import Path

from abletools.pack import build_demo_pack, validate_pack


if __name__ == "__main__":
    destination = build_demo_pack(Path("build/example-pack"), seed=1842)
    print(validate_pack(destination))
