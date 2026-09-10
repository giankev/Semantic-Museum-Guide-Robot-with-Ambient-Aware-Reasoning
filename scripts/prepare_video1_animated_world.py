#!/usr/bin/env python3
"""Create a disposable Video 1 world; never edit the accepted museum world."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

WALK_SHA256 = '49af0df3a319d1cb8ca2cebf02dbd00f625e5d5bec820bc5e109925b18b65c6e'
REMOVED = {'visitor_marker', 'guide_marker', 'staff_marker'}


def prepare(source, output, mode, config, walk_asset=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError('Refusing to overwrite the accepted world')
    tree = ET.parse(source)
    world = tree.getroot().find('world')
    # Source-relative resources must still resolve from the disposable world.
    for uri in world.iter('uri'):
        text = (uri.text or '').strip()
        if text and '://' not in text and not Path(text).is_absolute():
            resolved = source.parent / text
            if not resolved.is_file():
                raise ValueError(f'Missing world resource: {resolved}')
            uri.text = resolved.as_uri()
    if mode != 'static':
        for model in list(world.findall('model')):
            if model.get('name') in REMOVED:
                world.remove(model)
    camera = world.find('./gui/camera')
    camera.find('pose').text = '0 8 32 0 1.50 1.57079632679'
    asset_hash = None
    if mode == 'actor':
        if config['name'] != 'video1_walker_1' or config['identifier'] != 'walker_1':
            raise ValueError('Only the single-actor POC is supported before runtime validation')
        walk_asset = Path(walk_asset).resolve()
        asset_hash = hashlib.sha256(walk_asset.read_bytes()).hexdigest()
        if asset_hash != WALK_SHA256:
            raise ValueError(f'Unverified walk.dae asset: {asset_hash}; see docs/video1_animated_demo.md')
        a = config['phase']
        x = config['cx'] + config['rx'] * math.cos(a)
        y = config['cy'] + config['ry'] * math.sin(a)
        heading = math.atan2(config['ry'] * config['omega'] * math.cos(a),
                             -config['rx'] * config['omega'] * math.sin(a))
        actor = ET.SubElement(world, 'actor', name=config['name'])
        ET.SubElement(actor, 'pose').text = f'{x} {y} 1.2138 1.57079632679 0 {heading + math.pi/2}'
        skin = ET.SubElement(actor, 'skin')
        ET.SubElement(skin, 'filename').text = str(walk_asset)
        ET.SubElement(skin, 'scale').text = '1.0'
        animation = ET.SubElement(actor, 'animation', name='walking')
        ET.SubElement(animation, 'filename').text = str(walk_asset)
        ET.SubElement(animation, 'scale').text = '1.0'
        ET.SubElement(animation, 'interpolate_x').text = 'true'
        plugin = ET.SubElement(actor, 'plugin', name='video1_actor', filename='libvideo1_actor.so')
        for key in ('cx', 'cy', 'rx', 'ry', 'omega', 'phase'):
            if not math.isfinite(config[key]):
                raise ValueError('Nonfinite trajectory')
            ET.SubElement(plugin, key).text = str(config[key])
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return {'mode': mode, 'actor_count': int(mode == 'actor'),
            'source_world_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'generated_world_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'walk_sha256': asset_hash, 'trajectory': config if mode == 'actor' else None,
            'runtime_validation': 'NOT_RUN', 'visual_walking': 'NOT_VERIFIED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--mode', choices=('baseline', 'static', 'actor'), default='actor')
    parser.add_argument('--walk-asset')
    args = parser.parse_args()
    if args.mode == 'actor' and not args.walk_asset:
        assets = sorted(Path('/usr/share').glob('gazebo-11*/media/models/walk.dae'))
        if not assets:
            parser.error('Gazebo 11 walk.dae is missing INSIDE Docker; see the asset instructions')
        args.walk_asset = str(assets[0])
    manifest = prepare(args.source, args.output, args.mode,
                       json.loads(Path(args.config).read_text()), args.walk_asset)
    Path(args.output).with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
