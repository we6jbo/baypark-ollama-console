#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

MAAAZERUNNER_VERSION = '2026.07.20.2'

HOME = Path('/home/we6jbo')
PROJECT = Path('/opt/baypark-ollama-console')
OUTPUT_DIR = PROJECT
APP = OUTPUT_DIR / 'app.py'
WORLD = OUTPUT_DIR / 'adventure_world.json'
ENGINE = OUTPUT_DIR / 'adventure_world.py'
ANSWERS = OUTPUT_DIR / 'decision_tree_known_answers.json'
DRAFT_DIR = HOME / '.maaazerunner'
DRAFT = DRAFT_DIR / 'adventure_world.draft.json'
ANSWERS_DRAFT = DRAFT_DIR / 'decision_tree_known_answers.draft.json'
ANSWERS_IMPORT = HOME / 'Downloads/maaazeanswers.json'
BUNDLE_IMPORT = HOME / 'Downloads/maaazerunner_bundle.json'
BACKUPS = DRAFT_DIR / 'publish-backups'
LOG_FILE = DRAFT_DIR / 'scheduled-publish.log'
LAST_RESULT = DRAFT_DIR / 'last-publish-result.txt'
SCRIPT_PATH = HOME / 'maaazerunner.py'
TOOL_COPY = PROJECT / 'tools/maaazerunner.py'
SYSTEMD_USER_DIR = HOME / '.config/systemd/user'
SCHEDULE_SERVICE = SYSTEMD_USER_DIR / 'maaazerunner-publish.service'
SCHEDULE_TIMER = SYSTEMD_USER_DIR / 'maaazerunner-publish.timer'
NETWORK_ASSISTANT_URL = 'http://192.168.5.215/'
NETWORK_ASSISTANT_STEPS = (
    'Open http://192.168.5.215/ and enter: check updates. '
    'After it finishes, enter: version, reset game, and look.'
)
THANKS_TEXT = 'I, Jeremiah, thank you ChatGPT for helping me with this.'
AUTOSTART = HOME / '.config/autostart/maaazerunner.desktop'
AUTOSTART_MD5 = '7b040c10cb62c5ecb4ddce554ac8a28e'

TREASURES = [
    'amber_bear',
    'obsidian_handaxe',
    'shell_pendant',
    'red_ochre_stone',
    'carved_bone',
]

DEFAULT_ANSWERS = {
    'schema_version': 1,
    'answers': [
        {
            'id': 'roadmap-next',
            'enabled': True,
            'questions': [
                'whats next on the roadmap',
                'what is next on the roadmap',
                "what's next on the roadmap",
            ],
            'answer': (
                'The next step on the roadmap is to review the current project '
                'status, finish the highest-priority incomplete task, test that '
                'task, and document the result before adding another major feature.'
            ),
        },
        {
            'id': 'check-updates',
            'enabled': True,
            'questions': [
                'how do i check for updates',
                'how do i update network assistant',
                'check for updates',
            ],
            'answer': (
                'In Network Assistant AI, enter: check updates. After the update '
                'finishes, refresh the page and enter: version.'
            ),
        },
    ],
}

DEFAULT_WORLD = {
    'schema_version': 1,
    'title': 'The Five Treasures of the Hidden Valley',
    'start_room': 'sunlit_courtyard',
    'button_sequence': ['blue', 'amber', 'green'],
    'diamond_clue': 'Look at the diamond in the sun: blue, amber, then green.',
    'win_treasures': TREASURES,
    'lamp': {
        'item_id': 'rechargeable_lamp',
        'charger_room': 'lamp_workshop',
        'average_seconds_per_move': 18,
        'safety_multiplier': 1.45,
        'minimum_moves': 8,
    },
    'rooms': {
        'sunlit_courtyard': {
            'name': 'Sunlit Courtyard',
            'description': 'A diamond rests in direct sunlight.',
            'story': 'Five treasures are hidden beyond old engineering puzzles.',
            'exits': {'east': 'mill_room', 'north': 'prism_gallery'},
            'locked_exits': {},
            'items': ['sun_diamond'],
            'tags': ['sunlight'],
            'dark': False,
        },
        'mill_room': {
            'name': 'Water-Wheel Mill',
            'description': 'A water wheel drives a dangerous shaft.',
            'story': 'Use the wrench to turn off the wheel.',
            'exits': {'west': 'sunlit_courtyard', 'east': 'button_hall'},
            'locked_exits': {},
            'items': ['wrench'],
            'tags': ['water_wheel'],
            'dark': False,
        },
        'prism_gallery': {
            'name': 'Prism Gallery',
            'description': 'Sunlight separates into blue, amber, and green.',
            'story': 'Neanderthals made sophisticated tools, used pigments, and cared for injured community members.',
            'exits': {'south': 'sunlit_courtyard'},
            'locked_exits': {},
            'items': ['amber_bear'],
            'tags': ['neanderthal_fact'],
            'dark': False,
        },
        'button_hall': {
            'name': 'Three-Button Hall',
            'description': 'Three buttons glow blue, amber, and green.',
            'story': 'The diamond in sunlight reveals the operating sequence.',
            'exits': {'west': 'mill_room'},
            'locked_exits': {'east': 'trapdoor_room'},
            'items': [],
            'tags': ['button_puzzle'],
            'dark': False,
        },
        'trapdoor_room': {
            'name': 'Rug and Trapdoor Room',
            'description': 'A rug lies beside a fitted trapdoor.',
            'story': 'Place the rug, open the trapdoor, then go down.',
            'exits': {'west': 'button_hall'},
            'locked_exits': {'down': 'gas_room'},
            'items': ['door_rug'],
            'tags': ['trapdoor'],
            'dark': False,
        },
        'gas_room': {
            'name': 'Smelly Room',
            'description': 'Gas fills the room. A ventilation valve is nearby.',
            'story': 'A lit torch causes a big boom unless the valve clears the gas.',
            'exits': {'up': 'trapdoor_room', 'east': 'lamp_workshop'},
            'locked_exits': {},
            'items': ['torch', 'obsidian_handaxe'],
            'tags': ['gas_room', 'gas_valve'],
            'dark': True,
        },
        'lamp_workshop': {
            'name': 'Lamp Workshop',
            'description': 'A hand-cranked station recharges the lamp.',
            'story': 'Lamp life is based on average travel pace and distance back to this charger.',
            'exits': {'west': 'gas_room', 'north': 'neanderthal_gallery'},
            'locked_exits': {},
            'items': ['rechargeable_lamp', 'shell_pendant'],
            'tags': ['lamp_charger'],
            'dark': False,
        },
        'neanderthal_gallery': {
            'name': 'Neanderthal Gallery',
            'description': 'Displays cover shelters, pigments, hunting, and stone-tool traditions.',
            'story': 'Neanderthals lived across Europe and western Asia and adapted to varied climates.',
            'exits': {'south': 'lamp_workshop', 'east': 'treasure_vault'},
            'locked_exits': {},
            'items': ['red_ochre_stone'],
            'tags': ['neanderthal_fact'],
            'dark': False,
        },
        'treasure_vault': {
            'name': 'Five-Treasure Vault',
            'description': 'Five recesses surround a stone chest.',
            'story': 'Bring all five treasures here to win.',
            'exits': {'west': 'neanderthal_gallery'},
            'locked_exits': {},
            'items': ['carved_bone'],
            'tags': ['win_room'],
            'dark': False,
        },
    },
    'items': {
        'sun_diamond': {'name': 'sun diamond', 'description': 'A diamond that reveals colored light.', 'portable': True, 'treasure': False, 'tags': ['diamond']},
        'wrench': {'name': 'wrench', 'description': 'A wrench for the water-wheel shutoff.', 'portable': True, 'treasure': False, 'tags': ['water_wheel_tool']},
        'door_rug': {'name': 'rug', 'description': 'A rug that can be placed on the trapdoor.', 'portable': True, 'treasure': False, 'tags': ['trapdoor_rug']},
        'torch': {'name': 'torch', 'description': 'A flame source unsafe around gas.', 'portable': True, 'treasure': False, 'tags': ['flame']},
        'rechargeable_lamp': {'name': 'rechargeable lamp', 'description': 'A lamp with a limited charge.', 'portable': True, 'treasure': False, 'tags': ['lamp']},
        'amber_bear': {'name': 'amber bear', 'description': 'A carved amber bear.', 'portable': True, 'treasure': True, 'tags': ['treasure']},
        'obsidian_handaxe': {'name': 'obsidian handaxe', 'description': 'A ceremonial handaxe.', 'portable': True, 'treasure': True, 'tags': ['treasure', 'neanderthal']},
        'shell_pendant': {'name': 'shell pendant', 'description': 'A pierced shell pendant.', 'portable': True, 'treasure': True, 'tags': ['treasure', 'neanderthal']},
        'red_ochre_stone': {'name': 'red ochre stone', 'description': 'A shaped pigment stone.', 'portable': True, 'treasure': True, 'tags': ['treasure', 'neanderthal']},
        'carved_bone': {'name': 'carved bone', 'description': 'An incised bone object.', 'portable': True, 'treasure': True, 'tags': ['treasure', 'neanderthal']},
    },
}

ENGINE_SOURCE = r'''from __future__ import annotations
import json
import math
import os
import tempfile
import traceback
from collections import deque
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORLD_FILE = BASE / 'adventure_world.json'
STATE_FILE = BASE / 'adventure_player_state.json'

def load_world():
    return json.loads(WORLD_FILE.read_text(encoding='utf-8'))

def default_state(world):
    return {
        'room': world['start_room'],
        'inventory': [],
        'flags': {
            'wheel_off': False,
            'entrance_open': False,
            'rug_placed': False,
            'trapdoor_open': False,
            'gas_cleared': False,
            'torch_lit': False,
        },
        'buttons': [],
        'lamp_charge': 0,
        'moves': 0,
        'won': False,
    }

def load_state(world):
    try:
        value = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else default_state(world)
    except Exception:
        return default_state(world)

def save_state(state):
    fd, name = tempfile.mkstemp(prefix='.adventure-state-', dir=str(BASE))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write('\n')
        os.replace(name, STATE_FILE)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass

def norm(text):
    return ' '.join(text.lower().strip().split())

def item_id(world, phrase):
    wanted = norm(phrase)
    for key, value in world['items'].items():
        if wanted in {norm(key), norm(value.get('name', ''))}:
            return key
    return None

def room_text(world, state):
    room = world['rooms'][state['room']]
    parts = [room['name'], room['description']]
    if room.get('story'):
        parts.append(room['story'])
    visible = [world['items'][i]['name'] for i in room.get('items', []) if i in world['items']]
    if visible:
        parts.append('You can see: ' + ', '.join(visible) + '.')
    directions = sorted(set(room.get('exits', {})) | set(room.get('locked_exits', {})))
    if directions:
        parts.append('Directions: ' + ', '.join(directions) + '.')
    return '\n\n'.join(parts)

def distance(world, start, goal):
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        room_id, count = queue.popleft()
        if room_id == goal:
            return count
        room = world['rooms'].get(room_id, {})
        targets = list(room.get('exits', {}).values()) + list(room.get('locked_exits', {}).values())
        for target in targets:
            if target in world['rooms'] and target not in seen:
                seen.add(target)
                queue.append((target, count + 1))
    return None

def recommended_charge(world, room_id):
    lamp = world['lamp']
    steps = distance(world, room_id, lamp['charger_room'])
    minimum = int(lamp['minimum_moves'])
    if steps is None:
        return minimum
    seconds = steps * float(lamp['average_seconds_per_move']) * float(lamp['safety_multiplier'])
    moves = math.ceil(seconds / max(1.0, float(lamp['average_seconds_per_move']))) + 4
    return max(minimum, moves)

def handle_adventure_command(command):
    world = load_world()
    state = load_state(world)
    raw = command.strip()
    low = norm(raw)
    directions = {'north', 'south', 'east', 'west', 'up', 'down'}
    prefixes = (
        'take ', 'get ', 'examine ', 'inspect ', 'push ',
        'place rug', 'put rug', 'turn wheel', 'turn off water wheel',
        'use wrench on wheel', 'open trapdoor', 'turn valve',
        'vent gas', 'light torch', 'extinguish torch',
        'recharge lamp', 'lamp status', 'check lamp',
    )
    if low not in directions | {'look', 'inventory', 'reset game'} and not low.startswith(prefixes):
        return None
    if low == 'reset game':
        state = default_state(world)
        save_state(state)
        return 'The adventure has been reset.\n\n' + room_text(world, state)
    if low == 'look':
        return room_text(world, state)
    if low == 'inventory':
        if not state['inventory']:
            return 'You are carrying nothing.'
        return 'You are carrying: ' + ', '.join(world['items'][i]['name'] for i in state['inventory']) + '.'
    if low in {'lamp status', 'check lamp'}:
        return f"Lamp charge: {state['lamp_charge']} moves. Recommended reserve from here: {recommended_charge(world, state['room'])} moves."
    if low == 'recharge lamp':
        lamp_id = world['lamp']['item_id']
        if state['room'] != world['lamp']['charger_room']:
            return 'The lamp can only be recharged at the lamp workshop.'
        if lamp_id not in state['inventory']:
            return 'You need to carry the lamp.'
        state['lamp_charge'] = recommended_charge(world, state['room']) * 3
        save_state(state)
        return f"The lamp is recharged to {state['lamp_charge']} moves."
    if low.startswith(('take ', 'get ')):
        key = item_id(world, raw.split(' ', 1)[1])
        room = world['rooms'][state['room']]
        if not key or key not in room.get('items', []):
            return 'That item is not here.'
        room['items'].remove(key)
        state['inventory'].append(key)
        WORLD_FILE.write_text(json.dumps(world, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        save_state(state)
        return 'Taken: ' + world['items'][key]['name'] + '.'
    if low.startswith(('examine ', 'inspect ')):
        key = item_id(world, raw.split(' ', 1)[1])
        room = world['rooms'][state['room']]
        if not key or (key not in state['inventory'] and key not in room.get('items', [])):
            return 'You do not see that here.'
        item = world['items'][key]
        if 'diamond' in item.get('tags', []) and 'sunlight' in room.get('tags', []):
            return item['description'] + '\n\n' + world['diamond_clue']
        return item['description']
    if low in {'turn wheel', 'turn off water wheel', 'use wrench on wheel'}:
        if 'water_wheel' not in world['rooms'][state['room']].get('tags', []):
            return 'There is no water wheel here.'
        if 'wrench' not in state['inventory']:
            return 'The shutoff requires the wrench.'
        state['flags']['wheel_off'] = True
        save_state(state)
        return 'The water wheel slows and stops.'
    if low.startswith('push '):
        room = world['rooms'][state['room']]
        if 'button_puzzle' not in room.get('tags', []):
            return 'There are no colored buttons here.'
        color = norm(raw.split(' ', 1)[1])
        expected = world['button_sequence']
        state['buttons'].append(color)
        if state['buttons'] != expected[:len(state['buttons'])]:
            state['buttons'] = []
            save_state(state)
            return f'The {color} light flashes, then the controls reset.'
        if len(state['buttons']) == len(expected):
            state['flags']['entrance_open'] = True
            state['buttons'] = []
            save_state(state)
            return 'The entrance opens.'
        save_state(state)
        return f'The {color} button stays lit.'
    if low in {'place rug', 'place rug on trapdoor', 'put rug on trapdoor'}:
        if 'trapdoor' not in world['rooms'][state['room']].get('tags', []):
            return 'There is no trapdoor here.'
        if 'door_rug' not in state['inventory']:
            return 'You need the rug.'
        state['flags']['rug_placed'] = True
        save_state(state)
        return 'You place the rug on the trapdoor.'
    if low == 'open trapdoor':
        if 'trapdoor' not in world['rooms'][state['room']].get('tags', []):
            return 'There is no trapdoor here.'
        if not state['flags']['rug_placed']:
            return 'Place the rug first.'
        state['flags']['trapdoor_open'] = True
        save_state(state)
        return 'The trapdoor opens. You can go down.'
    if low in {'turn valve', 'vent gas'}:
        if 'gas_valve' not in world['rooms'][state['room']].get('tags', []):
            return 'There is no valve here.'
        state['flags']['gas_cleared'] = True
        save_state(state)
        return 'The valve clears the gas.'
    if low == 'light torch':
        if 'torch' not in state['inventory']:
            return 'You are not carrying the torch.'
        if 'gas_room' in world['rooms'][state['room']].get('tags', []) and not state['flags']['gas_cleared']:
            state = default_state(world)
            save_state(state)
            return 'BIG BOOM. The gas ignites and the adventure resets.'
        state['flags']['torch_lit'] = True
        save_state(state)
        return 'The torch is lit.'
    if low == 'extinguish torch':
        state['flags']['torch_lit'] = False
        save_state(state)
        return 'The torch is extinguished.'
    if low in directions:
        room = world['rooms'][state['room']]
        destination = room.get('exits', {}).get(low)
        locked = room.get('locked_exits', {}).get(low)
        if locked:
            if 'button_puzzle' in room.get('tags', []) and not state['flags']['entrance_open']:
                return 'The entrance is sealed by the colored-button controls.'
            if 'trapdoor' in room.get('tags', []) and low == 'down' and not state['flags']['trapdoor_open']:
                return 'The trapdoor is closed.'
            destination = locked
        if not destination:
            return 'There is no room in that direction.'
        if 'water_wheel' in room.get('tags', []) and low == 'east' and not state['flags']['wheel_off']:
            return 'The moving shaft blocks the way. Turn off the water wheel with the wrench.'
        target = world['rooms'][destination]
        if 'gas_room' in target.get('tags', []) and state['flags']['torch_lit'] and not state['flags']['gas_cleared']:
            state = default_state(world)
            save_state(state)
            return 'BIG BOOM. The lit torch enters the gas and the adventure resets.'
        lamp_id = world['lamp']['item_id']
        if target.get('dark') and lamp_id in state['inventory']:
            if state['lamp_charge'] <= 0:
                return 'The lamp is dead. Recharge it first.'
            state['lamp_charge'] -= 1
        state['room'] = destination
        state['moves'] += 1
        treasures = set(world['win_treasures'])
        if treasures.issubset(state['inventory']) and 'win_room' in target.get('tags', []):
            state['won'] = True
            save_state(state)
            return room_text(world, state) + '\n\nYou place all five treasures in the vault and win.'
        save_state(state)
        return room_text(world, state)
    return None
'''

def write_atomic(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass

def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def validate(world: dict) -> list[str]:
    errors = []
    rooms = world.get('rooms', {})
    items = world.get('items', {})
    if world.get('start_room') not in rooms:
        errors.append('The start room is missing.')
    room_tags = {tag for room in rooms.values() for tag in room.get('tags', [])}
    item_tags = {tag for item in items.values() for tag in item.get('tags', [])}
    required_room_tags = {
        'water_wheel': 'water wheel',
        'button_puzzle': 'three-button entrance',
        'trapdoor': 'rug/trapdoor puzzle',
        'gas_room': 'smelly gas room',
        'gas_valve': 'gas valve',
        'lamp_charger': 'lamp recharge room',
        'neanderthal_fact': 'Neanderthal facts',
        'win_room': 'win room',
        'sunlight': 'sunlight room for diamond clue',
    }
    for tag, label in required_room_tags.items():
        if tag not in room_tags:
            errors.append('Missing ' + label + f' (room tag {tag}).')
    required_item_tags = {
        'water_wheel_tool': 'wrench',
        'diamond': 'diamond',
        'trapdoor_rug': 'rug',
        'flame': 'torch',
        'lamp': 'rechargeable lamp',
    }
    for tag, label in required_item_tags.items():
        if tag not in item_tags:
            errors.append('Missing ' + label + f' (item tag {tag}).')
    treasures = world.get('win_treasures', [])
    if len(treasures) != 5 or len(set(treasures)) != 5:
        errors.append('The win condition must use exactly five unique treasures.')
    for key in treasures:
        if key not in items:
            errors.append(f'Missing treasure item {key}.')
        elif not items[key].get('treasure'):
            errors.append(f'{key} is not marked as a treasure.')
    if len(world.get('button_sequence', [])) != 3:
        errors.append('The button sequence must contain exactly three colors.')
    if not world.get('diamond_clue'):
        errors.append('The diamond-in-sun clue is missing.')
    lamp = world.get('lamp', {})
    if lamp.get('item_id') not in items:
        errors.append('The configured lamp item is missing.')
    if lamp.get('charger_room') not in rooms:
        errors.append('The configured lamp charger room is missing.')
    for room_id, room in rooms.items():
        for area in ('exits', 'locked_exits'):
            for direction, target in room.get(area, {}).items():
                if direction not in {'north', 'south', 'east', 'west', 'up', 'down'}:
                    errors.append(f'{room_id} has invalid direction {direction}.')
                if target not in rooms:
                    errors.append(f'{room_id} points to missing room {target}.')
        for item in room.get('items', []):
            if item not in items:
                errors.append(f'{room_id} contains missing item {item}.')
    return errors


def _bump_app_version(source: str) -> tuple[str, str]:
    match = re.search(r"(?m)^APP_VERSION\s*=\s*['\"](\d+)\.(\d+)\.(\d+)['\"]", source)
    if not match:
        return source, 'APP_VERSION was not changed.'
    major, minor, patch = map(int, match.groups())
    version = f'{major}.{minor}.{patch + 1}'
    updated = source[:match.start()] + f"APP_VERSION = '{version}'" + source[match.end():]
    return updated, 'APP_VERSION increased to ' + version + '.'


def patch_app(source: str, *, bump_version: bool = True) -> tuple[str, str]:
    tree = ast.parse(source)
    function = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'adventure_command':
            function = node
            break
    if function is None or not function.args.args:
        raise RuntimeError('app.py has no compatible top-level adventure_command function.')

    lines = source.splitlines(keepends=True)
    function_text = ''.join(lines[function.lineno - 1:function.end_lineno])
    already_hooked = (
        'from adventure_world import handle_adventure_command' in function_text
        and 'result = handle_adventure_command' in function_text
    )

    updated = source
    hook_note = 'The existing adventure hook was preserved.'
    if not already_hooked:
        argument = function.args.args[0].arg
        tuple_return = any(
            isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)
            for node in ast.walk(function)
        )
        indent = '    '
        if tuple_return:
            body = (
                f'{indent}from adventure_world import handle_adventure_command\n'
                f'{indent}result = handle_adventure_command({argument})\n'
                f'{indent}if result is None:\n'
                f'{indent}{indent}return "I am not sure how to do that.", clickable_links_html()\n'
                f'{indent}return result, clickable_links_html()\n'
            )
        else:
            body = (
                f'{indent}from adventure_world import handle_adventure_command\n'
                f'{indent}result = handle_adventure_command({argument})\n'
                f'{indent}if result is None:\n'
                f'{indent}{indent}return "I am not sure how to do that."\n'
                f'{indent}return result\n'
            )
        updated = ''.join(
            lines[:function.lineno - 1]
            + [lines[function.lineno - 1], body]
            + lines[function.end_lineno:]
        )
        hook_note = 'The latest app.py was hooked to the generated adventure engine.'

    version_note = 'APP_VERSION was not changed.'
    if bump_version:
        updated, version_note = _bump_app_version(updated)

    ast.parse(updated)
    return updated, hook_note + ' ' + version_note


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def _file_would_change(path: Path, content: str) -> bool:
    try:
        return path.read_text(encoding='utf-8') != content
    except FileNotFoundError:
        return True


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=PROJECT,
        check=check,
        text=True,
        capture_output=True,
    )


def _notify_user(title: str, body: str) -> None:
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', title, body], check=False)


def validate_answers_data(data: dict) -> list[str]:
    errors: list[str] = []
    entries = data.get('answers')
    if not isinstance(entries, list):
        return ['Prepopulated answers must contain an answers list.']
    seen: set[str] = set()
    normalized_questions: dict[str, str] = {}
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f'Answer entry {position} is not an object.')
            continue
        answer_id = str(entry.get('id', '')).strip()
        if not re.fullmatch(r'[a-z0-9_-]+', answer_id):
            errors.append(f'Answer entry {position} has an invalid ID.')
        elif answer_id in seen:
            errors.append(f'Duplicate answer ID: {answer_id}.')
        else:
            seen.add(answer_id)
        questions = entry.get('questions')
        if not isinstance(questions, list) or not any(str(q).strip() for q in questions):
            errors.append(f'{answer_id or "Unnamed answer"} needs at least one question.')
        else:
            for question in questions:
                normalized = ' '.join(str(question).casefold().split())
                if not normalized:
                    continue
                previous = normalized_questions.get(normalized)
                if previous and previous != answer_id:
                    errors.append(
                        f'Question {question!r} appears in both {previous} and {answer_id}.'
                    )
                normalized_questions[normalized] = answer_id
        if not str(entry.get('answer', '')).strip():
            errors.append(f'{answer_id or "Unnamed answer"} has no answer text.')
    return errors


def _merge_unique(existing: list, imported: list) -> list:
    result = list(existing)
    for value in imported:
        if value not in result:
            result.append(value)
    return result


def _merge_object_without_erasing(existing: dict, imported: dict) -> None:
    for key, value in imported.items():
        if key not in existing or existing[key] in ('', None, [], {}):
            existing[key] = json.loads(json.dumps(value))
        elif isinstance(existing[key], list) and isinstance(value, list):
            existing[key] = _merge_unique(existing[key], value)
        elif isinstance(existing[key], dict) and isinstance(value, dict):
            _merge_object_without_erasing(existing[key], value)


def merge_bundle(world: dict, answers_data: dict, bundle: dict) -> tuple[int, int, int]:
    imported_world = bundle.get('world', {})
    imported_answers = bundle.get('prepopulated_answers', bundle.get('answers', {}))
    if not isinstance(imported_world, dict):
        raise ValueError('The bundle world must be an object.')
    if isinstance(imported_answers, list):
        imported_answers = {'schema_version': 1, 'answers': imported_answers}
    if not isinstance(imported_answers, dict):
        raise ValueError('The bundle prepopulated_answers must be an object.')

    added_rooms = 0
    added_items = 0
    added_answers = 0

    for key, value in imported_world.items():
        if key in {'rooms', 'items'}:
            continue
        if key not in world or world[key] in ('', None, [], {}):
            world[key] = json.loads(json.dumps(value))

    world.setdefault('rooms', {})
    for room_id, room in imported_world.get('rooms', {}).items():
        if room_id not in world['rooms']:
            world['rooms'][room_id] = json.loads(json.dumps(room))
            added_rooms += 1
        elif isinstance(room, dict):
            _merge_object_without_erasing(world['rooms'][room_id], room)

    world.setdefault('items', {})
    for item_id, item in imported_world.get('items', {}).items():
        if item_id not in world['items']:
            world['items'][item_id] = json.loads(json.dumps(item))
            added_items += 1
        elif isinstance(item, dict):
            _merge_object_without_erasing(world['items'][item_id], item)

    answers_data.setdefault('answers', [])
    by_id = {
        str(entry.get('id', '')): entry
        for entry in answers_data['answers']
        if isinstance(entry, dict)
    }
    for entry in imported_answers.get('answers', []):
        if not isinstance(entry, dict):
            continue
        answer_id = str(entry.get('id', '')).strip()
        if not answer_id:
            continue
        if answer_id not in by_id:
            copy = json.loads(json.dumps(entry))
            answers_data['answers'].append(copy)
            by_id[answer_id] = copy
            added_answers += 1
        else:
            current = by_id[answer_id]
            current['questions'] = _merge_unique(
                list(current.get('questions', [])),
                list(entry.get('questions', [])),
            )
            if not str(current.get('answer', '')).strip():
                current['answer'] = str(entry.get('answer', ''))
            if 'enabled' not in current:
                current['enabled'] = bool(entry.get('enabled', True))

    return added_rooms, added_items, added_answers


def _version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r'\d+', value)
    return tuple(int(number) for number in numbers) if numbers else (0,)


def publish_payload(
    world: dict,
    answers_data: dict,
    *,
    hook_app: bool,
    commit_message: str,
) -> str:
    errors = validate(world) + validate_answers_data(answers_data)
    if errors:
        raise RuntimeError('Validation failed:\n' + '\n'.join('• ' + item for item in errors))
    if not (PROJECT / '.git').is_dir():
        raise RuntimeError(f'{PROJECT} is not a Git working tree.')
    if not APP.exists():
        raise RuntimeError(f'The verified latest app.py is missing: {APP}')

    porcelain = _git('status', '--porcelain').stdout.strip()
    if porcelain:
        raise RuntimeError(
            'The Git working tree is not clean. Commit, stash, or remove unrelated '
            'changes before publishing:\n' + porcelain
        )

    _git('pull', '--ff-only', 'origin', 'main')

    # Never let an older running MaaazeRunner overwrite a newer copy that was
    # already pulled from GitHub. Older repository copies without this version
    # marker are treated as version 0 and can be upgraded safely.
    if TOOL_COPY.exists():
        repo_source = TOOL_COPY.read_text(encoding='utf-8')
        match = re.search(
            r"(?m)^MAAAZERUNNER_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            repo_source,
        )
        repo_version = match.group(1) if match else '0'
        if _version_key(repo_version) > _version_key(MAAAZERUNNER_VERSION):
            raise RuntimeError(
                'GitHub contains a newer MaaazeRunner than the running copy. '
                f'Repository version: {repo_version}; running version: '
                f'{MAAAZERUNNER_VERSION}. Copy tools/maaazerunner.py to '
                f'{SCRIPT_PATH}, compile it, and run the schedule again.'
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    world_text = _json_text(world)
    engine_text = ENGINE_SOURCE
    answers_text = _json_text(answers_data)
    script_text = SCRIPT_PATH.read_text(encoding='utf-8')
    data_changed = any((
        _file_would_change(WORLD, world_text),
        _file_would_change(ENGINE, engine_text),
        _file_would_change(ANSWERS, answers_text),
        _file_would_change(TOOL_COPY, script_text),
    ))

    if not data_changed:
        result = 'No MaaazeRunner data changes were found, so no commit was created.'
        write_atomic(LAST_RESULT, result + '\n', 0o600)
        return result

    for path in (APP, WORLD, ENGINE, ANSWERS, TOOL_COPY):
        if path.exists():
            backup_name = path.name if path != TOOL_COPY else 'tools-maaazerunner.py'
            shutil.copy2(path, BACKUPS / f'{backup_name}.{stamp}.bak')

    write_atomic(WORLD, world_text)
    write_atomic(ENGINE, engine_text)
    write_atomic(ANSWERS, answers_text)
    write_atomic(TOOL_COPY, script_text, 0o755)
    subprocess.run(
        [sys.executable, '-m', 'py_compile', str(ENGINE)],
        check=True,
        text=True,
        capture_output=True,
    )

    note = 'app.py was preserved without modification.'
    if hook_app:
        latest_source = APP.read_text(encoding='utf-8')
        updated, note = patch_app(latest_source, bump_version=True)
        write_atomic(APP, updated)
        subprocess.run(
            [sys.executable, '-m', 'py_compile', str(APP)],
            check=True,
            text=True,
            capture_output=True,
        )

    relative_files = [
        str(WORLD.relative_to(PROJECT)),
        str(ENGINE.relative_to(PROJECT)),
        str(ANSWERS.relative_to(PROJECT)),
        str(TOOL_COPY.relative_to(PROJECT)),
    ]
    if hook_app:
        relative_files.append(str(APP.relative_to(PROJECT)))

    _git('add', '--', *relative_files)
    staged = _git('diff', '--cached', '--name-status').stdout.strip()
    if not staged:
        result = 'Generated files already matched Git. No commit was created.'
        write_atomic(LAST_RESULT, result + '\n', 0o600)
        return result

    _git('diff', '--cached', '--check')
    _git('commit', '-m', commit_message)
    _git('push', 'origin', 'main')

    result = (
        f'Published successfully at {datetime.now().isoformat(timespec="seconds")}.\n'
        f'{note}\nStaged and pushed:\n{staged}\n\n{NETWORK_ASSISTANT_STEPS}'
    )
    write_atomic(LAST_RESULT, result + '\n', 0o600)
    _notify_user('MaaazeRunner published', NETWORK_ASSISTANT_STEPS)
    return result


def install_schedule_files() -> None:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    service = f'''[Unit]
Description=MaaazeRunner scheduled GitHub publisher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={PROJECT}
ExecStart=/usr/bin/python3 {SCRIPT_PATH} --scheduled-publish
'''
    timer = '''[Unit]
Description=Run MaaazeRunner publishing four times daily outside the daytime blackout

[Timer]
OnCalendar=*-*-* 00:05:00
OnCalendar=*-*-* 15:30:00
OnCalendar=*-*-* 17:30:00
OnCalendar=*-*-* 19:40:00
Persistent=true
Unit=maaazerunner-publish.service

[Install]
WantedBy=timers.target
'''
    write_atomic(SCHEDULE_SERVICE, service, 0o644)
    write_atomic(SCHEDULE_TIMER, timer, 0o644)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(
        ['systemctl', '--user', 'enable', '--now', SCHEDULE_TIMER.name],
        check=True,
    )


def remove_schedule_files() -> None:
    subprocess.run(
        ['systemctl', '--user', 'disable', '--now', SCHEDULE_TIMER.name],
        check=False,
    )
    SCHEDULE_SERVICE.unlink(missing_ok=True)
    SCHEDULE_TIMER.unlink(missing_ok=True)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=False)


def scheduled_publish() -> int:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    # Scheduled GitHub automation is prohibited from 07:00 through 15:20
    # local time. This also blocks Persistent=true catch-up runs after boot.
    now = datetime.now()
    minutes_now = now.hour * 60 + now.minute
    blackout_start = 7 * 60
    blackout_end = 15 * 60 + 20
    if blackout_start <= minutes_now <= blackout_end:
        result = (
            'Scheduled publish skipped because the local time falls inside '
            'the protected 07:00-15:20 GitHub automation blackout.\n'
            f'Current local time: {now.isoformat(timespec="seconds")}\n\n'
            f'{NETWORK_ASSISTANT_STEPS}'
        )
        write_atomic(LAST_RESULT, result + '\n', 0o600)
        with LOG_FILE.open('a', encoding='utf-8') as handle:
            handle.write(result + '\n')
        return 0

    try:
        # A brand-new repository may not contain generated adventure files yet.
        # Prefer saved drafts, then existing generated files, and finally use
        # the built-in complete defaults. This creates missing outputs rather
        # than failing or deleting any existing rooms, items, or answers.
        if DRAFT.exists():
            world = json.loads(DRAFT.read_text(encoding='utf-8'))
        elif WORLD.exists():
            world = json.loads(WORLD.read_text(encoding='utf-8'))
        else:
            world = json.loads(json.dumps(DEFAULT_WORLD))

        if ANSWERS_DRAFT.exists():
            answers = json.loads(ANSWERS_DRAFT.read_text(encoding='utf-8'))
        elif ANSWERS.exists():
            answers = json.loads(ANSWERS.read_text(encoding='utf-8'))
        else:
            answers = json.loads(json.dumps(DEFAULT_ANSWERS))

        # Save the exact payload used by the scheduler so later GUI sessions
        # and support exports reproduce the same content.
        write_atomic(DRAFT, _json_text(world), 0o600)
        write_atomic(ANSWERS_DRAFT, _json_text(answers), 0o600)
        result = publish_payload(
            world,
            answers,
            hook_app=True,
            commit_message='Scheduled MaaazeRunner adventure update',
        )
        with LOG_FILE.open('a', encoding='utf-8') as handle:
            handle.write(f'\n[{datetime.now().isoformat(timespec="seconds")}] SUCCESS\n{result}\n')
        return 0
    except Exception:
        details = traceback.format_exc()
        with LOG_FILE.open('a', encoding='utf-8') as handle:
            handle.write(f'\n[{datetime.now().isoformat(timespec="seconds")}] FAILURE\n{details}\n')
        write_atomic(LAST_RESULT, 'Scheduled publish failed:\n' + details, 0o600)
        _notify_user('MaaazeRunner publish failed', f'Review {LOG_FILE}')
        return 1

class Builder:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title('MaaazeRunner Adventure Builder')
        self.root.geometry('1100x760')
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        self.world = self.load_world()
        self.answers_data = self.load_answers()
        self.status = tk.StringVar(value='Ready.')
        self.hook = tk.BooleanVar(value=True)
        self.make_ui()
        self.refresh_lists()
        self.refresh_answer_list()
        self.refresh_json()
        self.refresh_schedule_status()

    def load_world(self) -> dict:
        for path in (DRAFT, WORLD):
            if path.exists():
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(value, dict):
                        return value
                except Exception:
                    pass
        return json.loads(json.dumps(DEFAULT_WORLD))

    def load_answers(self) -> dict:
        for path in (ANSWERS_DRAFT, ANSWERS):
            if path.exists():
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(value, dict) and isinstance(value.get('answers'), list):
                        return value
                except Exception:
                    pass
        return json.loads(json.dumps(DEFAULT_ANSWERS))

    def make_ui(self) -> None:
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill='x')
        ttk.Button(top, text='Save Draft', command=self.save_draft).pack(side='left', padx=3)
        ttk.Button(top, text='Validate', command=self.show_validation).pack(side='left', padx=3)
        ttk.Button(top, text='Publish to GitHub', command=self.publish).pack(side='left', padx=3)
        ttk.Button(top, text='Uninstall Autostart', command=self.uninstall).pack(side='right', padx=3)

        book = ttk.Notebook(self.root)
        book.pack(fill='both', expand=True, padx=6, pady=4)
        self.room_tab = ttk.Frame(book, padding=8)
        self.item_tab = ttk.Frame(book, padding=8)
        self.answers_tab = ttk.Frame(book, padding=8)
        self.json_tab = ttk.Frame(book, padding=8)
        self.bundle_tab = ttk.Frame(book, padding=8)
        self.schedule_tab = ttk.Frame(book, padding=8)
        self.thanks_tab = ttk.Frame(book, padding=8)
        self.validation_tab = ttk.Frame(book, padding=8)
        book.add(self.room_tab, text='Rooms and Story')
        book.add(self.item_tab, text='Items')
        book.add(self.answers_tab, text='Prepopulated Questions')
        book.add(self.json_tab, text='World JSON')
        book.add(self.bundle_tab, text='Import / Export Everything')
        book.add(self.schedule_tab, text='Automatic Publishing')
        book.add(self.thanks_tab, text='Thanks')
        book.add(self.validation_tab, text='Validation')

        self.make_rooms()
        self.make_items()
        self.make_answers()
        self.make_json()
        self.make_bundle()
        self.make_schedule()
        self.make_thanks()
        self.make_validation()
        ttk.Checkbutton(top, text='Hook generated engine into app.py', variable=self.hook).pack(side='left', padx=12)
        ttk.Label(self.root, textvariable=self.status, relief='sunken', anchor='w').pack(fill='x', padx=6, pady=4)

    def make_rooms(self) -> None:
        left = ttk.Frame(self.room_tab)
        left.pack(side='left', fill='y')
        right = ttk.Frame(self.room_tab)
        right.pack(side='right', fill='both', expand=True, padx=(10, 0))
        self.rooms = tk.Listbox(left, width=32)
        self.rooms.pack(fill='y', expand=True)
        self.rooms.bind('<<ListboxSelect>>', self.select_room)
        ttk.Button(left, text='New Room', command=self.new_room).pack(fill='x', pady=2)
        ttk.Button(left, text='Delete Room', command=self.delete_room).pack(fill='x', pady=2)
        self.room_id = ttk.Entry(right)
        self.room_name = ttk.Entry(right)
        self.room_desc = ScrolledText(right, height=5, wrap='word')
        self.room_story = ScrolledText(right, height=5, wrap='word')
        self.room_exits = ScrolledText(right, height=4, wrap='none')
        self.room_locked = ScrolledText(right, height=4, wrap='none')
        self.room_items = ttk.Entry(right)
        self.room_tags = ttk.Entry(right)
        self.room_dark = tk.BooleanVar()
        widgets = [
            ('Room ID', self.room_id), ('Name', self.room_name),
            ('Description', self.room_desc), ('Story / facts', self.room_story),
            ('Exits JSON', self.room_exits), ('Locked exits JSON', self.room_locked),
            ('Item IDs, comma-separated', self.room_items),
            ('Tags, comma-separated', self.room_tags),
        ]
        for row, (label, widget) in enumerate(widgets):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky='nw', pady=2)
            widget.grid(row=row, column=1, sticky='nsew', padx=5, pady=2)
        ttk.Checkbutton(right, text='Dark room', variable=self.room_dark).grid(row=8, column=1, sticky='w')
        ttk.Button(right, text='Save Room', command=self.save_room).grid(row=9, column=1, sticky='e', pady=5)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        self.current_room = None

    def make_items(self) -> None:
        left = ttk.Frame(self.item_tab)
        left.pack(side='left', fill='y')
        right = ttk.Frame(self.item_tab)
        right.pack(side='right', fill='both', expand=True, padx=(10, 0))
        self.items = tk.Listbox(left, width=32)
        self.items.pack(fill='y', expand=True)
        self.items.bind('<<ListboxSelect>>', self.select_item)
        ttk.Button(left, text='New Item', command=self.new_item).pack(fill='x', pady=2)
        ttk.Button(left, text='Delete Item', command=self.delete_item).pack(fill='x', pady=2)
        self.item_id = ttk.Entry(right)
        self.item_name = ttk.Entry(right)
        self.item_desc = ScrolledText(right, height=8, wrap='word')
        self.item_tags = ttk.Entry(right)
        self.item_portable = tk.BooleanVar(value=True)
        self.item_treasure = tk.BooleanVar()
        widgets = [('Item ID', self.item_id), ('Name', self.item_name), ('Description', self.item_desc), ('Tags, comma-separated', self.item_tags)]
        for row, (label, widget) in enumerate(widgets):
            ttk.Label(right, text=label).grid(row=row, column=0, sticky='nw', pady=2)
            widget.grid(row=row, column=1, sticky='nsew', padx=5, pady=2)
        ttk.Checkbutton(right, text='Portable', variable=self.item_portable).grid(row=4, column=1, sticky='w')
        ttk.Checkbutton(right, text='Treasure', variable=self.item_treasure).grid(row=5, column=1, sticky='w')
        ttk.Button(right, text='Save Item', command=self.save_item).grid(row=6, column=1, sticky='e', pady=5)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        self.current_item = None

    def make_answers(self) -> None:
        left = ttk.Frame(self.answers_tab)
        left.pack(side='left', fill='y')
        right = ttk.Frame(self.answers_tab)
        right.pack(side='right', fill='both', expand=True, padx=(10, 0))

        self.answer_list = tk.Listbox(left, width=34)
        self.answer_list.pack(fill='y', expand=True)
        self.answer_list.bind('<<ListboxSelect>>', self.select_answer)

        ttk.Button(left, text='New Answer', command=self.new_answer).pack(fill='x', pady=2)
        ttk.Button(left, text='Delete Answer', command=self.delete_answer).pack(fill='x', pady=2)
        ttk.Separator(left).pack(fill='x', pady=6)
        ttk.Button(
            left,
            text='Import maaazeanswers.json',
            command=self.import_answers,
        ).pack(fill='x', pady=2)
        ttk.Button(
            left,
            text='Export maaazeanswers.json',
            command=self.export_answers,
        ).pack(fill='x', pady=2)

        self.answer_id = ttk.Entry(right)
        self.answer_enabled = tk.BooleanVar(value=True)
        self.answer_questions = ScrolledText(right, height=9, wrap='word')
        self.answer_text = ScrolledText(right, height=12, wrap='word')

        ttk.Label(right, text='Answer ID').grid(row=0, column=0, sticky='w', pady=2)
        self.answer_id.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        ttk.Checkbutton(
            right,
            text='Enabled for automatic matching',
            variable=self.answer_enabled,
        ).grid(row=1, column=1, sticky='w', pady=2)
        ttk.Label(
            right,
            text='Accepted question wording, one question per line',
        ).grid(row=2, column=0, sticky='nw', pady=2)
        self.answer_questions.grid(row=2, column=1, sticky='nsew', padx=5, pady=2)
        ttk.Label(right, text='Answer to send').grid(row=3, column=0, sticky='nw', pady=2)
        self.answer_text.grid(row=3, column=1, sticky='nsew', padx=5, pady=2)
        ttk.Button(right, text='Save Answer', command=self.save_answer).grid(
            row=4, column=1, sticky='e', pady=6
        )

        ttk.Label(
            right,
            text=(
                'Default import/export file: '
                '/home/we6jbo/Downloads/maaazeanswers.json'
            ),
        ).grid(row=5, column=1, sticky='w', pady=4)

        right.columnconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)
        right.rowconfigure(3, weight=1)
        self.current_answer = None

    def make_json(self) -> None:
        ttk.Button(self.json_tab, text='Apply JSON', command=self.apply_json).pack(anchor='w')
        ttk.Button(self.json_tab, text='Refresh JSON', command=self.refresh_json).pack(anchor='w', pady=3)
        self.json_text = ScrolledText(self.json_tab, wrap='none')
        self.json_text.pack(fill='both', expand=True)

    def make_bundle(self) -> None:
        ttk.Label(
            self.bundle_tab,
            text='Import adds missing rooms, items, exits, tags, and questions. Existing content is not erased.',
            wraplength=900,
        ).pack(anchor='w', pady=(0, 8))
        ttk.Button(
            self.bundle_tab,
            text='Import and Add from maaazerunner_bundle.json',
            command=self.import_bundle,
        ).pack(anchor='w', pady=3)
        ttk.Button(
            self.bundle_tab,
            text='Export Everything to maaazerunner_bundle.json',
            command=self.export_bundle,
        ).pack(anchor='w', pady=3)
        ttk.Label(self.bundle_tab, text=f'Default file: {BUNDLE_IMPORT}').pack(anchor='w', pady=8)
        self.bundle_report = ScrolledText(self.bundle_tab, height=20, wrap='word')
        self.bundle_report.pack(fill='both', expand=True)

    def make_schedule(self) -> None:
        ttk.Label(
            self.schedule_tab,
            text='Automatic GitHub publishing times: 12:05 AM, 10:00 AM, 3:30 PM, and 7:40 PM.',
            wraplength=900,
        ).pack(anchor='w', pady=(0, 8))
        controls = ttk.Frame(self.schedule_tab)
        controls.pack(anchor='w')
        ttk.Button(controls, text='Install / Enable Schedule', command=self.install_schedule).pack(side='left', padx=3)
        ttk.Button(controls, text='Disable Schedule', command=self.remove_schedule).pack(side='left', padx=3)
        ttk.Button(controls, text='Run Scheduled Publish Now', command=self.run_scheduled_now).pack(side='left', padx=3)
        ttk.Button(controls, text='Refresh Status', command=self.refresh_schedule_status).pack(side='left', padx=3)
        self.schedule_status = ScrolledText(self.schedule_tab, height=18, wrap='word')
        self.schedule_status.pack(fill='both', expand=True, pady=8)
        ttk.Label(self.schedule_tab, text=NETWORK_ASSISTANT_STEPS, wraplength=900).pack(anchor='w', pady=4)

    def make_thanks(self) -> None:
        ttk.Label(self.thanks_tab, text='Thanks', font=('TkDefaultFont', 18, 'bold')).pack(anchor='center', pady=(30, 15))
        ttk.Label(
            self.thanks_tab,
            text=THANKS_TEXT,
            wraplength=760,
            justify='center',
            font=('TkDefaultFont', 13),
        ).pack(anchor='center')

    def make_validation(self) -> None:
        ttk.Button(self.validation_tab, text='Run Validation', command=self.show_validation).pack(anchor='w')
        self.validation_text = ScrolledText(self.validation_tab, wrap='word')
        self.validation_text.pack(fill='both', expand=True, pady=5)

    def refresh_lists(self) -> None:
        self.rooms.delete(0, 'end')
        for key in sorted(self.world['rooms']):
            self.rooms.insert('end', key)
        self.items.delete(0, 'end')
        for key in sorted(self.world['items']):
            self.items.insert('end', key)

    def select_room(self, _event=None) -> None:
        if not self.rooms.curselection():
            return
        key = self.rooms.get(self.rooms.curselection()[0])
        self.current_room = key
        room = self.world['rooms'][key]
        for widget, value in [(self.room_id, key), (self.room_name, room.get('name', '')), (self.room_items, ', '.join(room.get('items', []))), (self.room_tags, ', '.join(room.get('tags', [])))]:
            widget.delete(0, 'end')
            widget.insert(0, value)
        for widget, value in [(self.room_desc, room.get('description', '')), (self.room_story, room.get('story', '')), (self.room_exits, json.dumps(room.get('exits', {}), indent=2)), (self.room_locked, json.dumps(room.get('locked_exits', {}), indent=2))]:
            widget.delete('1.0', 'end')
            widget.insert('1.0', value)
        self.room_dark.set(bool(room.get('dark')))

    def select_item(self, _event=None) -> None:
        if not self.items.curselection():
            return
        key = self.items.get(self.items.curselection()[0])
        self.current_item = key
        item = self.world['items'][key]
        for widget, value in [(self.item_id, key), (self.item_name, item.get('name', '')), (self.item_tags, ', '.join(item.get('tags', [])))]:
            widget.delete(0, 'end')
            widget.insert(0, value)
        self.item_desc.delete('1.0', 'end')
        self.item_desc.insert('1.0', item.get('description', ''))
        self.item_portable.set(bool(item.get('portable', True)))
        self.item_treasure.set(bool(item.get('treasure', False)))

    def new_room(self) -> None:
        key = simpledialog.askstring('New Room', 'Room ID:')
        if not key:
            return
        key = key.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]+', key) or key in self.world['rooms']:
            messagebox.showerror('Invalid Room', 'Use a unique lowercase ID with letters, numbers, and underscores.')
            return
        self.world['rooms'][key] = {'name': key.replace('_', ' ').title(), 'description': '', 'story': '', 'exits': {}, 'locked_exits': {}, 'items': [], 'tags': [], 'dark': False}
        self.refresh_lists()

    def new_item(self) -> None:
        key = simpledialog.askstring('New Item', 'Item ID:')
        if not key:
            return
        key = key.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]+', key) or key in self.world['items']:
            messagebox.showerror('Invalid Item', 'Use a unique lowercase ID with letters, numbers, and underscores.')
            return
        self.world['items'][key] = {'name': key.replace('_', ' '), 'description': '', 'portable': True, 'treasure': False, 'tags': []}
        self.refresh_lists()

    def save_room(self) -> None:
        if not self.current_room:
            return
        new_key = self.room_id.get().strip().lower()
        try:
            exits = json.loads(self.room_exits.get('1.0', 'end').strip() or '{}')
            locked = json.loads(self.room_locked.get('1.0', 'end').strip() or '{}')
        except json.JSONDecodeError as exc:
            messagebox.showerror('Invalid JSON', str(exc))
            return
        room = {'name': self.room_name.get().strip(), 'description': self.room_desc.get('1.0', 'end').strip(), 'story': self.room_story.get('1.0', 'end').strip(), 'exits': exits, 'locked_exits': locked, 'items': [x.strip() for x in self.room_items.get().split(',') if x.strip()], 'tags': [x.strip() for x in self.room_tags.get().split(',') if x.strip()], 'dark': self.room_dark.get()}
        if new_key != self.current_room:
            if new_key in self.world['rooms']:
                messagebox.showerror('Duplicate', 'That room ID already exists.')
                return
            del self.world['rooms'][self.current_room]
            for other in self.world['rooms'].values():
                for area in ('exits', 'locked_exits'):
                    for direction, target in list(other.get(area, {}).items()):
                        if target == self.current_room:
                            other[area][direction] = new_key
            if self.world['start_room'] == self.current_room:
                self.world['start_room'] = new_key
        self.world['rooms'][new_key] = room
        self.current_room = new_key
        self.refresh_lists()
        self.refresh_json()

    def save_item(self) -> None:
        if not self.current_item:
            return
        new_key = self.item_id.get().strip().lower()
        item = {'name': self.item_name.get().strip(), 'description': self.item_desc.get('1.0', 'end').strip(), 'portable': self.item_portable.get(), 'treasure': self.item_treasure.get(), 'tags': [x.strip() for x in self.item_tags.get().split(',') if x.strip()]}
        if new_key != self.current_item:
            if new_key in self.world['items']:
                messagebox.showerror('Duplicate', 'That item ID already exists.')
                return
            del self.world['items'][self.current_item]
            for room in self.world['rooms'].values():
                room['items'] = [new_key if x == self.current_item else x for x in room.get('items', [])]
            self.world['win_treasures'] = [new_key if x == self.current_item else x for x in self.world.get('win_treasures', [])]
        self.world['items'][new_key] = item
        self.current_item = new_key
        self.refresh_lists()
        self.refresh_json()

    def delete_room(self) -> None:
        if self.current_room and messagebox.askyesno('Delete Room', 'Delete ' + self.current_room + '?'):
            del self.world['rooms'][self.current_room]
            self.current_room = None
            self.refresh_lists()
            self.refresh_json()

    def delete_item(self) -> None:
        if self.current_item and messagebox.askyesno('Delete Item', 'Delete ' + self.current_item + '?'):
            del self.world['items'][self.current_item]
            for room in self.world['rooms'].values():
                room['items'] = [x for x in room.get('items', []) if x != self.current_item]
            self.current_item = None
            self.refresh_lists()
            self.refresh_json()

    def refresh_answer_list(self) -> None:
        self.answer_list.delete(0, 'end')
        entries = self.answers_data.setdefault('answers', [])
        for entry in sorted(entries, key=lambda item: str(item.get('id', ''))):
            marker = '' if entry.get('enabled', True) else ' [disabled]'
            self.answer_list.insert('end', str(entry.get('id', 'unnamed')) + marker)

    def _find_answer_index(self, answer_id: str) -> int | None:
        for index, entry in enumerate(self.answers_data.get('answers', [])):
            if str(entry.get('id', '')) == answer_id:
                return index
        return None

    def select_answer(self, _event=None) -> None:
        if not self.answer_list.curselection():
            return
        display = self.answer_list.get(self.answer_list.curselection()[0])
        answer_id = display.removesuffix(' [disabled]')
        index = self._find_answer_index(answer_id)
        if index is None:
            return
        entry = self.answers_data['answers'][index]
        self.current_answer = answer_id
        self.answer_id.delete(0, 'end')
        self.answer_id.insert(0, answer_id)
        self.answer_enabled.set(bool(entry.get('enabled', True)))
        self.answer_questions.delete('1.0', 'end')
        self.answer_questions.insert(
            '1.0',
            '\n'.join(str(value) for value in entry.get('questions', [])),
        )
        self.answer_text.delete('1.0', 'end')
        self.answer_text.insert('1.0', str(entry.get('answer', '')))

    def new_answer(self) -> None:
        answer_id = simpledialog.askstring(
            'New Prepopulated Answer',
            'Enter a unique answer ID using lowercase letters, numbers, hyphens, or underscores:',
        )
        if not answer_id:
            return
        answer_id = answer_id.strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]+', answer_id):
            messagebox.showerror(
                'Invalid ID',
                'Use lowercase letters, numbers, hyphens, and underscores only.',
            )
            return
        if self._find_answer_index(answer_id) is not None:
            messagebox.showerror('Duplicate ID', 'That answer ID already exists.')
            return
        self.answers_data.setdefault('answers', []).append({
            'id': answer_id,
            'enabled': True,
            'questions': [],
            'answer': '',
        })
        self.current_answer = answer_id
        self.refresh_answer_list()
        for index in range(self.answer_list.size()):
            if self.answer_list.get(index).startswith(answer_id):
                self.answer_list.selection_clear(0, 'end')
                self.answer_list.selection_set(index)
                self.answer_list.see(index)
                break
        self.select_answer()

    def save_answer(self) -> None:
        if not self.current_answer:
            messagebox.showerror('No Answer Selected', 'Select or create an answer first.')
            return
        new_id = self.answer_id.get().strip().lower()
        if not re.fullmatch(r'[a-z0-9_-]+', new_id):
            messagebox.showerror(
                'Invalid ID',
                'Use lowercase letters, numbers, hyphens, and underscores only.',
            )
            return
        existing = self._find_answer_index(new_id)
        current_index = self._find_answer_index(self.current_answer)
        if current_index is None:
            messagebox.showerror('Missing Answer', 'The selected answer could not be found.')
            return
        if existing is not None and existing != current_index:
            messagebox.showerror('Duplicate ID', 'That answer ID already exists.')
            return
        questions = [
            line.strip()
            for line in self.answer_questions.get('1.0', 'end').splitlines()
            if line.strip()
        ]
        answer = self.answer_text.get('1.0', 'end').strip()
        self.answers_data['answers'][current_index] = {
            'id': new_id,
            'enabled': self.answer_enabled.get(),
            'questions': questions,
            'answer': answer,
        }
        self.current_answer = new_id
        self.refresh_answer_list()
        self.status.set(f'Saved prepopulated answer {new_id}.')

    def delete_answer(self) -> None:
        if not self.current_answer:
            return
        if not messagebox.askyesno(
            'Delete Answer',
            f'Delete prepopulated answer {self.current_answer}?',
        ):
            return
        index = self._find_answer_index(self.current_answer)
        if index is not None:
            del self.answers_data['answers'][index]
        self.current_answer = None
        self.refresh_answer_list()
        self.answer_id.delete(0, 'end')
        self.answer_questions.delete('1.0', 'end')
        self.answer_text.delete('1.0', 'end')

    def validate_answers(self) -> list[str]:
        return validate_answers_data(self.answers_data)

    def import_answers(self) -> None:
        path = ANSWERS_IMPORT
        if not path.exists():
            messagebox.showerror('Import File Missing', f'Create or copy the import file here:\n{path}')
            return
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(value, list):
                value = {'schema_version': 1, 'answers': value}
            if not isinstance(value, dict) or not isinstance(value.get('answers'), list):
                raise ValueError('The file must contain an "answers" list.')
            before = len(self.answers_data.get('answers', []))
            merge_bundle(self.world, self.answers_data, {'prepopulated_answers': value})
            errors = self.validate_answers()
            if errors:
                raise ValueError('\n'.join(errors))
            added = len(self.answers_data.get('answers', [])) - before
        except Exception as exc:
            messagebox.showerror('Import Failed', str(exc))
            return
        self.current_answer = None
        self.refresh_answer_list()
        self.status.set(f'Imported answers additively from {path}. Added {added} new answer IDs.')
        messagebox.showinfo('Import Complete', f'Added {added} new answer IDs. Existing answers were preserved.')

    def export_answers(self) -> None:
        errors = self.validate_answers()
        if errors:
            messagebox.showerror(
                'Cannot Export',
                'Fix these problems first:\n\n' + '\n'.join('• ' + error for error in errors),
            )
            return
        write_atomic(
            ANSWERS_IMPORT,
            json.dumps(self.answers_data, indent=2, sort_keys=True) + '\n',
            0o600,
        )
        self.status.set(f'Exported prepopulated answers to {ANSWERS_IMPORT}.')
        messagebox.showinfo('Export Complete', f'Saved:\n{ANSWERS_IMPORT}')

    def import_bundle(self) -> None:
        if not BUNDLE_IMPORT.exists():
            messagebox.showerror('Import File Missing', f'Create or copy the bundle here:\n{BUNDLE_IMPORT}')
            return
        try:
            bundle = json.loads(BUNDLE_IMPORT.read_text(encoding='utf-8'))
            if not isinstance(bundle, dict):
                raise ValueError('The bundle must be a JSON object.')
            counts = merge_bundle(self.world, self.answers_data, bundle)
            errors = validate(self.world) + self.validate_answers()
            if errors:
                raise ValueError('\n'.join(errors))
        except Exception as exc:
            messagebox.showerror('Bundle Import Failed', str(exc))
            return
        self.refresh_lists()
        self.refresh_answer_list()
        self.refresh_json()
        self.save_draft()
        report = (
            f'Imported additively from {BUNDLE_IMPORT}\n'
            f'New rooms: {counts[0]}\nNew items: {counts[1]}\n'
            f'New answer IDs: {counts[2]}\n'
            'Existing content was not erased. Missing nested exits, tags, items, and question variants were added.'
        )
        self.bundle_report.delete('1.0', 'end')
        self.bundle_report.insert('1.0', report)
        messagebox.showinfo('Bundle Import Complete', report)

    def export_bundle(self) -> None:
        errors = validate(self.world) + self.validate_answers()
        if errors:
            messagebox.showerror('Cannot Export', 'Fix these problems first:\n\n' + '\n'.join('• ' + e for e in errors))
            return
        bundle = {
            'schema_version': 1,
            'generated_at': datetime.now().isoformat(timespec='seconds'),
            'thanks': THANKS_TEXT,
            'network_assistant_url': NETWORK_ASSISTANT_URL,
            'network_assistant_update_steps': NETWORK_ASSISTANT_STEPS,
            'world': self.world,
            'prepopulated_answers': self.answers_data,
            'source_files': {
                'app': str(APP),
                'world': str(WORLD),
                'engine': str(ENGINE),
                'answers': str(ANSWERS),
            },
        }
        write_atomic(BUNDLE_IMPORT, _json_text(bundle), 0o600)
        report = (
            f'Exported all rooms, items, world settings, and prepopulated answers to:\n{BUNDLE_IMPORT}\n\n'
            'You can share this file for diagnosis or an additive import repair.'
        )
        self.bundle_report.delete('1.0', 'end')
        self.bundle_report.insert('1.0', report)
        messagebox.showinfo('Export Complete', report)

    def install_schedule(self) -> None:
        try:
            install_schedule_files()
        except Exception as exc:
            messagebox.showerror('Schedule Installation Failed', str(exc))
            return
        self.refresh_schedule_status()
        messagebox.showinfo('Schedule Enabled', 'Automatic publishing is enabled for 12:05 AM, 10:00 AM, 3:30 PM, and 7:40 PM.')

    def remove_schedule(self) -> None:
        remove_schedule_files()
        self.refresh_schedule_status()
        messagebox.showinfo('Schedule Disabled', 'Automatic publishing has been disabled.')

    def run_scheduled_now(self) -> None:
        self.save_draft()
        result = subprocess.run(
            ['systemctl', '--user', 'start', SCHEDULE_SERVICE.name],
            text=True,
            capture_output=True,
        )
        self.refresh_schedule_status()
        if result.returncode:
            messagebox.showerror('Scheduled Publish Failed to Start', result.stderr or result.stdout)
        else:
            messagebox.showinfo('Scheduled Publish Started', f'Review the status and log.\n\n{NETWORK_ASSISTANT_STEPS}')

    def refresh_schedule_status(self) -> None:
        if not hasattr(self, 'schedule_status'):
            return
        result = subprocess.run(
            ['systemctl', '--user', 'status', SCHEDULE_TIMER.name, '--no-pager'],
            text=True,
            capture_output=True,
        )
        timer_list = subprocess.run(
            ['systemctl', '--user', 'list-timers', SCHEDULE_TIMER.name, '--no-pager'],
            text=True,
            capture_output=True,
        )
        last = LAST_RESULT.read_text(encoding='utf-8') if LAST_RESULT.exists() else 'No publish result has been recorded yet.'
        content = (
            (result.stdout or result.stderr)
            + '\n\n'
            + (timer_list.stdout or timer_list.stderr)
            + '\n\nLast result:\n'
            + last
            + '\n\nAfter a successful update:\n'
            + NETWORK_ASSISTANT_STEPS
        )
        self.schedule_status.delete('1.0', 'end')
        self.schedule_status.insert('1.0', content)

    def refresh_json(self) -> None:
        self.json_text.delete('1.0', 'end')
        self.json_text.insert('1.0', json.dumps(self.world, indent=2, sort_keys=True))

    def apply_json(self) -> None:
        try:
            value = json.loads(self.json_text.get('1.0', 'end'))
            if not isinstance(value, dict):
                raise ValueError('Top-level value must be an object.')
        except Exception as exc:
            messagebox.showerror('Invalid JSON', str(exc))
            return
        self.world = value
        self.refresh_lists()
        self.status.set('JSON applied.')

    def save_draft(self) -> None:
        write_atomic(DRAFT, json.dumps(self.world, indent=2, sort_keys=True) + '\n', 0o600)
        write_atomic(ANSWERS_DRAFT, json.dumps(self.answers_data, indent=2, sort_keys=True) + '\n', 0o600)
        self.status.set('World and prepopulated-answer drafts saved.')

    def show_validation(self) -> None:
        errors = validate(self.world) + self.validate_answers()
        self.validation_text.delete('1.0', 'end')
        if errors:
            self.validation_text.insert('1.0', 'Not ready to publish:\n\n' + '\n'.join('• ' + x for x in errors))
            self.status.set(f'{len(errors)} validation problem(s).')
        else:
            self.validation_text.insert('1.0', 'Validation passed. Required puzzles, Neanderthal facts, five treasures, and the win condition are present.')
            self.status.set('Validation passed.')

    def uninstall(self) -> None:
        if not AUTOSTART.exists():
            messagebox.showinfo('Uninstall', 'The autostart file does not exist.')
            return
        actual = md5(AUTOSTART)
        if actual != AUTOSTART_MD5:
            messagebox.showerror('Uninstall Refused', f'MD5 does not match.\n\nExpected: {AUTOSTART_MD5}\nActual: {actual}')
            return
        destination = Path('/tmp') / AUTOSTART.name
        if destination.exists():
            destination = Path('/tmp') / f'maaazerunner-{datetime.now():%Y%m%d-%H%M%S}.desktop'
        shutil.move(str(AUTOSTART), str(destination))
        messagebox.showinfo('Uninstalled', 'Moved the verified autostart file to:\n' + str(destination))

    def publish(self) -> None:
        errors = validate(self.world) + self.validate_answers()
        if errors:
            self.show_validation()
            messagebox.showerror('Cannot Publish', 'Required elements are missing. Review the Validation tab.')
            return
        if not messagebox.askyesno(
            'Publish Latest Version',
            'Save drafts, pull the latest GitHub main branch, back up the current output, generate the maze files, commit, and push?',
        ):
            return
        self.save_draft()
        message = simpledialog.askstring(
            'Commit Message',
            'Commit message:',
            initialvalue='Update MaaazeRunner adventure and known answers',
        )
        if not message:
            return
        try:
            result = publish_payload(
                self.world,
                self.answers_data,
                hook_app=self.hook.get(),
                commit_message=message,
            )
            self.refresh_schedule_status()
            messagebox.showinfo('Publish Result', result)
        except subprocess.CalledProcessError as exc:
            messagebox.showerror('Command Failed', (exc.stderr or exc.stdout or str(exc))[-4000:])
        except Exception as exc:
            messagebox.showerror('Publish Failed', str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(description='MaaazeRunner Adventure Builder')
    parser.add_argument('--scheduled-publish', action='store_true')
    parser.add_argument('--install-schedule', action='store_true')
    parser.add_argument('--remove-schedule', action='store_true')
    args = parser.parse_args()

    if args.install_schedule:
        install_schedule_files()
        print('MaaazeRunner schedule installed and enabled.')
        return
    if args.remove_schedule:
        remove_schedule_files()
        print('MaaazeRunner schedule removed.')
        return
    if args.scheduled_publish:
        raise SystemExit(scheduled_publish())

    root = tk.Tk()
    Builder(root)
    root.mainloop()

if __name__ == '__main__':
    main()
