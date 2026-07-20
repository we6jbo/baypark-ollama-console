from __future__ import annotations
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
