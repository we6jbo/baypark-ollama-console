#!/usr/bin/env python3
import concurrent.futures
import datetime
import hashlib
import html
import http.server
import ipaddress
import json
import os
import platform
import re
import shutil
import sqlite3
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

APP_DIR = Path('/opt/baypark-ollama-console')
APP_PATH = APP_DIR / 'app.py'
CONFIG_PATH = APP_DIR / 'config.json'
ADVENTURE_STATE_PATH = APP_DIR / 'adventure_state.json'
PERMISSION_REPAIR_LOG_PATH = APP_DIR / 'update-permission-repair.log'
DECISION_QUEUE_DB = Path('/var/lib/baypark-decision-queue/questions.sqlite3')
APP_VERSION = '7.609.1'
MAX_FETCH_BYTES = 160000
FETCH_TIMEOUT = 10
RESTART_REQUESTED = False


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(errors='replace'))
    except Exception:
        return default


def save_json(path, data):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(tmp, path)


def load_config():
    cfg = load_json(CONFIG_PATH, {})
    cfg.setdefault('version', APP_VERSION)
    cfg.setdefault('github_repo', 'we6jbo/baypark-ollama-console')
    cfg.setdefault('github_branch', 'main')
    cfg.setdefault('auto_update_on_unknown', True)
    return cfg


CONFIG = load_config()


def esc(value):
    return html.escape(str(value), quote=True)


def now_iso():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def read_file(path, default=''):
    try:
        return Path(path).read_text(errors='replace')
    except Exception:
        return default


def run_command(args, timeout=10):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as exc:
        return 1, '', f'{type(exc).__name__}: {exc}'


def get_ip_addresses():
    rc, out, _ = run_command(['hostname', '-I'], 3)
    return out.split() if rc == 0 and out else []


def mem_stats():
    values = {}
    for line in read_file('/proc/meminfo').splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            values[parts[0].rstrip(':')] = int(parts[1])
    total = values.get('MemTotal', 0)
    available = values.get('MemAvailable', 0)
    used = max(total - available, 0)
    return {
        'total_mb': round(total / 1024, 1),
        'available_mb': round(available / 1024, 1),
        'used_mb': round(used / 1024, 1),
        'used_percent': round((used / total) * 100, 2) if total else 0,
    }


def cpu_usage_percent():
    try:
        def read_cpu():
            fields = [int(x) for x in read_file('/proc/stat').splitlines()[0].split()[1:]]
            return fields[3] + fields[4], sum(fields)
        idle1, total1 = read_cpu()
        time.sleep(0.15)
        idle2, total2 = read_cpu()
        delta = total2 - total1
        return round(100 * (1 - ((idle2 - idle1) / delta)), 2) if delta > 0 else 0.0
    except Exception:
        return 0.0


def disk_stats():
    usage = shutil.disk_usage('/')
    return {
        'root_total_gb': round(usage.total / 1024**3, 2),
        'root_used_gb': round(usage.used / 1024**3, 2),
        'root_free_gb': round(usage.free / 1024**3, 2),
        'root_used_percent': round(usage.used / usage.total * 100, 2),
    }


def all_stats():
    uptime = read_file('/proc/uptime').split()
    uptime_seconds = int(float(uptime[0])) if uptime else 0
    return {
        'time': now_iso(),
        'hostname': socket.gethostname(),
        'ip_addresses': get_ip_addresses(),
        'uptime_seconds': uptime_seconds,
        'os': {
            'platform': platform.platform(),
            'release': platform.release(),
            'machine': platform.machine(),
            'python': platform.python_version(),
        },
        'cpu_percent': cpu_usage_percent(),
        'memory': mem_stats(),
        'disk': disk_stats(),
        'verification_file_exists': Path(CONFIG.get('verification_file', '/opt/machine-verification/9I0Sv4cnRO.txt')).exists(),
    }


def load_sources():
    return load_json(CONFIG.get('sources_file', str(APP_DIR / 'sources.json')), [])


def normalize_source_name(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower().strip()).strip('-')


def find_source(name):
    wanted = normalize_source_name(name)
    aliases = {
        'crime': 'crime-report', 'crime-reports': 'crime-report',
        'power': 'power-outages', 'outage': 'power-outages', 'outages': 'power-outages',
        'news': 'news-report', 'environment': 'environmental-factors',
        'environmental': 'environmental-factors',
    }
    wanted = aliases.get(wanted, wanted)
    for source in load_sources():
        if normalize_source_name(source.get('name', '')) == wanted:
            return source
    return None


def strip_html(text):
    text = re.sub(r'(?is)<script.*?</script>', ' ', text)
    text = re.sub(r'(?is)<style.*?</style>', ' ', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def summarize_rss(name, status, final_url, content_type, text):
    try:
        root = ET.fromstring(text)
        items = []
        for item in root.findall('.//item')[:8]:
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            description = strip_html(item.findtext('description') or '')[:280]
            if title:
                items.append(f'- {title}\n  {link}\n  {description}')
        if not items:
            namespace = '{http://www.w3.org/2005/Atom}'
            for entry in root.findall(f'.//{namespace}entry')[:8]:
                title = (entry.findtext(f'{namespace}title') or '').strip()
                link_element = entry.find(f'{namespace}link')
                link = link_element.attrib.get('href', '') if link_element is not None else ''
                summary = strip_html(entry.findtext(f'{namespace}summary') or '')[:280]
                if title:
                    items.append(f'- {title}\n  {link}\n  {summary}')
        if not items:
            return f"Source: {name}\nHTTP status: {status}\nThe feed was reachable, but no ordinary items were found."
        return f"Source: {name}\nHTTP status: {status}\nFinal URL: {final_url}\nContent-Type: {content_type}\n\nItems:\n" + '\n\n'.join(items)
    except Exception as exc:
        return f"Source '{name}' could not be parsed as a feed: {type(exc).__name__}: {exc}"


def safe_fetch_source(source):
    name = source.get('name', 'unknown')
    url = source.get('url', '')
    protocol = source.get('protocol', 'https').lower().strip()
    parsed = urllib.parse.urlparse(url)
    if protocol not in {'http', 'https', 'rss', 'txt'} or parsed.scheme not in {'http', 'https'}:
        return f"Source '{name}' has an unsupported protocol or URL."
    try:
        request = urllib.request.Request(url, headers={'User-Agent': f'NetworkAssistantAI/{APP_VERSION}'})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            status = getattr(response, 'status', 'unknown')
            final_url = response.geturl()
            content_type = response.headers.get('Content-Type', 'unknown')
            raw = response.read(MAX_FETCH_BYTES)
        text = raw.decode('utf-8', errors='replace')
        if protocol == 'rss' or 'xml' in content_type.lower() or 'rss' in content_type.lower():
            return summarize_rss(name, status, final_url, content_type, text)
        body = strip_html(text) if protocol in {'http', 'https'} else text
        return (
            f"Source: {name}\nDescription: {source.get('description', '')}\n"
            f"HTTP status: {status}\nFinal URL: {final_url}\nContent-Type: {content_type}\n\n"
            f"Retrieved information:\n{body[:4000]}"
        )
    except Exception as exc:
        return f"Problem fetching source '{name}': {type(exc).__name__}: {exc}"


def clickable_links_html():
    links = [('Network Assistant AI home', '/'), ('Local BBS', CONFIG.get('bbs_url', ''))]
    links.extend((source.get('display_name', source.get('name', 'Source')), source.get('url', '')) for source in load_sources())
    return '\n'.join(
        f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a>'
        for label, url in links if str(url).startswith(('http://', 'https://'))
    )


def adventure_default():
    return {'location': 'west_of_house', 'inventory': [], 'mailbox_open': False, 'leaflet_taken': False}


def adventure_state():
    return load_json(ADVENTURE_STATE_PATH, adventure_default())


def save_adventure_state(state):
    save_json(ADVENTURE_STATE_PATH, state)


def room_description(state):
    if state['location'] == 'west_of_house':
        mailbox = 'The small mailbox is open.' if state['mailbox_open'] else 'There is a small mailbox here.'
        return f'You are standing west of a white house. {mailbox}'
    if state['location'] == 'inside_house':
        return 'You are inside the house. A dusty network console hums quietly. The exit is west.'
    if state['location'] == 'north_path':
        return 'You are on a narrow path north of the house. A weathered sign says Network Update Test Successful. The house is south.'
    return 'You are in a quiet, unfinished room.'


def adventure_command(prompt):
    from adventure_world import handle_adventure_command
    result = handle_adventure_command(prompt)
    if result is None:
        return "I am not sure how to do that.", clickable_links_html()
    return result, clickable_links_html()


def github_raw_url(filename):
    repo = CONFIG.get('github_repo', 'we6jbo/baypark-ollama-console')
    branch = CONFIG.get('github_branch', 'main')
    return f'https://raw.githubusercontent.com/{repo}/{branch}/{filename}'


def download_bytes(url, limit=600000):
    request = urllib.request.Request(url, headers={'User-Agent': f'NetworkAssistantAI/{APP_VERSION}'})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        if response.geturl().split('/')[2] not in {'raw.githubusercontent.com', 'github.com'}:
            raise ValueError('Unexpected update host')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Remote update file is too large')
    return data


def version_tuple(value):
    parts = []
    for piece in str(value).strip().split('.'):
        match = re.match(r'(\d+)', piece)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def app_version_from_bytes(data):
    text = data.decode('utf-8', errors='strict')
    match = re.search(r"(?m)^APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text)
    if not match:
        raise ValueError('Remote app.py has no APP_VERSION')
    return match.group(1)


def validate_update(filename, data):
    if filename == 'app.py':
        compile(data.decode('utf-8'), filename, 'exec')
        if b'APP_DIR' not in data or b'Network Assistant AI' not in data:
            raise ValueError('Remote app.py did not pass identity checks')
        remote_version = app_version_from_bytes(data)
        if version_tuple(remote_version) < version_tuple(APP_VERSION):
            raise ValueError(f'Refusing downgrade from {APP_VERSION} to {remote_version}')
    elif filename.endswith('.json'):
        json.loads(data.decode('utf-8'))


def atomic_install(filename, data):
    destination = APP_DIR / filename
    if destination.exists() and destination.read_bytes() == data:
        return False
    backup_dir = APP_DIR / 'update-backups'
    backup_dir.mkdir(exist_ok=True)
    if destination.exists():
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(destination, backup_dir / f'{filename}.{stamp}.bak')
    temp = destination.with_suffix(destination.suffix + '.new')
    temp.write_bytes(data)
    if destination.exists():
        os.chmod(temp, destination.stat().st_mode)
    os.replace(temp, destination)
    return True


def check_github_updates():
    global RESTART_REQUESTED
    if not CONFIG.get('auto_update_on_unknown', True):
        return 'Automatic update checks are disabled.', False
    changed = []
    unavailable = []
    errors = []
    for filename in ('app.py', 'sources.json'):
        try:
            data = download_bytes(github_raw_url(filename))
            validate_update(filename, data)
            if atomic_install(filename, data):
                changed.append(filename)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                unavailable.append(filename)
            else:
                errors.append(f'{filename}: HTTP {exc.code}')
        except Exception as exc:
            errors.append(f'{filename}: {type(exc).__name__}: {exc}')
    if 'app.py' in changed:
        RESTART_REQUESTED = True
    parts = []
    if changed:
        parts.append('Installed GitHub updates: ' + ', '.join(changed) + '.')
    else:
        parts.append('No newer file content was found on GitHub.')
    if unavailable:
        parts.append('Not yet present in the repository: ' + ', '.join(unavailable) + '.')
    if errors:
        parts.append('Update check problems: ' + '; '.join(errors))
    return ' '.join(parts), bool(changed)


def local_ipv4_network():
    rc, out, _ = run_command(['ip', '-4', 'route', 'get', '1.1.1.1'], 4)
    match = re.search(r'\bsrc\s+(\d+\.\d+\.\d+\.\d+)', out)
    if not match:
        return None, None
    address = ipaddress.ip_address(match.group(1))
    rc, addr_out, _ = run_command(['ip', '-o', '-4', 'addr', 'show'], 4)
    for line in addr_out.splitlines():
        found = re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)', line)
        if found and ipaddress.ip_interface(found.group(1)).ip == address:
            interface = ipaddress.ip_interface(found.group(1))
            network = interface.network
            if network.num_addresses > 256:
                network = ipaddress.ip_network(f'{address}/24', strict=False)
            return address, network
    return address, ipaddress.ip_network(f'{address}/24', strict=False)


def ping_host(address):
    rc, _, _ = run_command(['ping', '-c', '1', '-W', '1', str(address)], 2)
    return str(address) if rc == 0 else None


def check_netnut():
    indicators = []
    details = []
    keywords = ('netnut', 'popa', 'residential proxy', 'proxy sdk', 'badbox')
    rc, process_text, _ = run_command(['ps', 'auxww'], 8)
    for line in process_text.splitlines():
        if any(keyword in line.lower() for keyword in keywords):
            indicators.append('Suspicious process text: ' + line[:240])
    if shutil.which('ss'):
        rc, connections, _ = run_command(['ss', '-tunap'], 10)
        for line in connections.splitlines():
            if any(keyword in line.lower() for keyword in keywords):
                indicators.append('Suspicious connection text: ' + line[:240])
        details.append('Active connection table checked.')
    address, network = local_ipv4_network()
    live = []
    if network:
        hosts = [host for host in network.hosts() if host != address]
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            for result in pool.map(ping_host, hosts):
                if result:
                    live.append(result)
        details.append(f'Local network checked: {network}; {len(live)} responding address(es).')
    rc, neighbors, _ = run_command(['ip', 'neigh', 'show'], 6)
    neighbor_lines = [line for line in neighbors.splitlines() if line.strip()]
    details.append(f'Neighbor table entries: {len(neighbor_lines)}.')
    for line in neighbor_lines:
        if any(keyword in line.lower() for keyword in keywords):
            indicators.append('Suspicious neighbor text: ' + line)
    for path in ('/etc/hosts', '/etc/resolv.conf'):
        content = read_file(path).lower()
        if any(keyword in content for keyword in keywords):
            indicators.append(f'Keyword found in {path}.')
    status = 'No obvious NetNut/Popa indicators were found by this basic scan.' if not indicators else 'Possible indicators need investigation:\n- ' + '\n- '.join(indicators)
    return (
        'NetNut defensive check\n'
        f'{status}\n\n' + '\n'.join(details) +
        '\nResponding addresses: ' + (', '.join(live[:80]) if live else 'none detected') +
        '\n\nThis is a basic local-network and Raspberry Pi check, not proof that every Android, TV, or streaming device is clean. '
        'Review unfamiliar devices, remove untrusted apps, update firmware, and use built-in device security scans.'
    )


def simple_check():
    lines = []
    rc, route, err = run_command(['ip', 'route', 'show', 'default'], 4)
    lines.append('Default route: ' + (route if route else f'not found ({err})'))
    try:
        addresses = socket.getaddrinfo('example.com', 443, type=socket.SOCK_STREAM)
        unique = sorted({item[4][0] for item in addresses})
        lines.append('DNS: working; example.com -> ' + ', '.join(unique[:4]))
    except Exception as exc:
        lines.append(f'DNS: failed: {type(exc).__name__}: {exc}')
    try:
        request = urllib.request.Request('https://example.com/', headers={'User-Agent': f'NetworkAssistantAI/{APP_VERSION}'})
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            lines.append(f'HTTPS: working; status {getattr(response, "status", "unknown")}')
    except Exception as exc:
        lines.append(f'HTTPS: failed: {type(exc).__name__}: {exc}')
    return 'Simple connection check\n' + '\n'.join(lines)


def system_status_text():
    stats = all_stats()
    hours, remainder = divmod(stats['uptime_seconds'], 3600)
    minutes = remainder // 60
    return (
        'System status\n'
        f"Time: {stats['time']}\nHostname: {stats['hostname']}\n"
        f"Running: yes\nUptime: {hours}h {minutes}m\n"
        f"IP addresses: {', '.join(stats['ip_addresses']) or 'none'}\n"
        f"OS: {stats['os']['platform']}\nArchitecture: {stats['os']['machine']}\n"
        f"Python: {stats['os']['python']}\nCPU usage: {stats['cpu_percent']}%\n"
        f"Memory: {stats['memory']['used_percent']}% used ({stats['memory']['used_mb']} MB of {stats['memory']['total_mb']} MB)\n"
        f"Storage: {stats['disk']['root_used_percent']}% used ({stats['disk']['root_free_gb']} GB free)\n"
        f"Verification file exists: {stats['verification_file_exists']}"
    )


def permission_repair_log_text(max_lines=80):
    """Summarize the local permission self-repair event log."""
    path = PERMISSION_REPAIR_LOG_PATH
    if not path.exists():
        return (
            f"No permission-repair event log exists yet at {path}.\n"
            "That usually means the repair service has not needed to fix anything, "
            "or the service has not created the log yet."
        )
    try:
        raw_lines = path.read_text(errors='replace').splitlines()
    except PermissionError:
        return (
            f"The log exists at {path}, but Network Assistant AI cannot read it. "
            "Run: sudo chown pi:pi " + str(path) + " && sudo chmod 664 " + str(path)
        )
    except Exception as exc:
        return f"Could not read {path}: {type(exc).__name__}: {exc}"

    lines = [line.strip() for line in raw_lines if line.strip()]
    if not lines:
        return f"The permission-repair log exists at {path}, but it is empty."

    recent = lines[-max_lines:]
    owner_repairs = sum('Repaired owner' in line for line in recent)
    mode_repairs = sum('Repaired mode' in line for line in recent)
    completions = sum('completed successfully' in line.lower() for line in recent)
    failures = [line for line in recent if re.search(r'fail|error|cannot|unsuccessful', line, re.I)]

    latest = recent[-1]
    if failures:
        condition = 'The log contains a possible failure or warning that should be reviewed.'
    elif owner_repairs or mode_repairs:
        condition = 'The service detected incorrect ownership or permissions and repaired them.'
    elif completions:
        condition = 'The latest recorded repair completed successfully.'
    else:
        condition = 'The log contains informational events, with no obvious failure detected.'

    excerpt = '\n'.join(recent[-20:])
    return (
        "Permission self-repair log summary:\n"
        f"Log file: {path}\n"
        f"Events examined: {len(recent)}"
        + (f" of {len(lines)} total" if len(lines) > len(recent) else '') + "\n"
        f"Ownership repairs: {owner_repairs}\n"
        f"Mode repairs: {mode_repairs}\n"
        f"Successful completion records: {completions}\n"
        f"Possible warning/failure records: {len(failures)}\n"
        f"Current interpretation: {condition}\n"
        f"Latest event: {latest}\n\n"
        "Most recent log entries:\n" + excerpt
    )


def github_update_help_text():
    return (
        "To engage the GitHub updater, enter: check updates\n\n"
        "The updater also runs automatically when Network Assistant AI does not recognize a command, "
        "when a requested saved source is missing, or when a movement direction has no room. "
        "For a deliberate test, enter an obviously unsupported command such as: github update trigger test\n\n"
        "Repository: https://github.com/" + str(CONFIG.get('github_repo')) + "\n"
        "Branch: " + str(CONFIG.get('github_branch')) + "\n"
        "After app.py is installed, the program requests a restart. Wait a few seconds, refresh the page, "
        "and enter: version"
    )



def decision_db_connect():
    DECISION_QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DECISION_QUEUE_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            question TEXT NOT NULL,
            extra_context TEXT,
            raw_email_id TEXT,
            submitted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            answer TEXT,
            answered_at TEXT,
            sent_at TEXT
        )
    """)
    conn.commit()
    return conn


def pending_questions_text(limit=20):
    try:
        with decision_db_connect() as conn:
            rows = conn.execute(
                "SELECT id, request_id, question, submitted_at FROM questions WHERE status='pending' ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
    except Exception as exc:
        return f"Decision queue could not be read: {type(exc).__name__}: {exc}"
    if not rows:
        return 'There are no pending Decision Tree Assistant questions.'
    lines = ['Pending Decision Tree Assistant questions:']
    for row in rows:
        summary = re.sub(r'\s+', ' ', row['question']).strip()
        if len(summary) > 180:
            summary = summary[:177] + '...'
        lines.append(f"{row['id']}. Request {row['request_id']} ({row['submitted_at']})\n   {summary}")
    lines.append('\nUse: open question NUMBER')
    lines.append('To answer: answer question NUMBER YOUR ANSWER')
    return '\n'.join(lines)


def open_question_text(question_id):
    try:
        with decision_db_connect() as conn:
            row = conn.execute('SELECT * FROM questions WHERE id=?', (question_id,)).fetchone()
    except Exception as exc:
        return f"Decision queue could not be read: {type(exc).__name__}: {exc}"
    if row is None:
        return f'Question {question_id} was not found.'
    return (
        f"Question {row['id']}\nRequest ID: {row['request_id']}\nStatus: {row['status']}\n"
        f"Submitted: {row['submitted_at']}\nQuestion:\n{row['question']}\n\n"
        f"Extra context:\n{row['extra_context'] or '(none)'}\n\nAnswer:\n{row['answer'] or '(not answered yet)'}"
    )


def answer_question_text(question_id, answer_text):
    answer_text = answer_text.strip()
    if not answer_text:
        return 'The answer is empty. Use: answer question NUMBER YOUR ANSWER'
    if len(answer_text) > 12000:
        return 'The answer is too long. Keep it under 12,000 characters.'
    try:
        with decision_db_connect() as conn:
            row = conn.execute('SELECT status FROM questions WHERE id=?', (question_id,)).fetchone()
            if row is None:
                return f'Question {question_id} was not found.'
            if row['status'] == 'sent':
                return f'Question {question_id} was already sent by email and cannot be changed here.'
            conn.execute("UPDATE questions SET answer=?, status='answered', answered_at=? WHERE id=?", (answer_text, now_iso(), question_id))
            conn.commit()
        return f'Answer saved for question {question_id}. The existing dt-out email process will send it on its next polling cycle.'
    except Exception as exc:
        return f"The answer could not be saved: {type(exc).__name__}: {exc}"


def decision_queue_status_text():
    try:
        with decision_db_connect() as conn:
            counts = {row['status']: row['count'] for row in conn.execute('SELECT status, COUNT(*) AS count FROM questions GROUP BY status').fetchall()}
            latest = conn.execute('SELECT id, request_id, status, submitted_at FROM questions ORDER BY id DESC LIMIT 1').fetchone()
    except Exception as exc:
        return f"Decision queue status is unavailable: {type(exc).__name__}: {exc}"
    lines = [
        'Decision Tree human-answer queue status:',
        f"Pending: {counts.get('pending', 0)}",
        f"Answered and waiting for email: {counts.get('answered', 0)}",
        f"Sent: {counts.get('sent', 0)}",
    ]
    if latest:
        lines.append(f"Latest: question {latest['id']}, request {latest['request_id']}, status {latest['status']}, submitted {latest['submitted_at']}")
    return '\n'.join(lines)


def decision_tree_github_help_text():
    repo = CONFIG.get('github_repo', 'we6jbo/baypark-ollama-console')
    branch = CONFIG.get('github_branch', 'main')
    command = (
        "sudo bash -c \"$(curl -fsSL "
        f"https://raw.githubusercontent.com/{repo}/{branch}/install-decision-tree-integration.sh)\""
    )
    return (
        'Decision Tree email integration update:\n'
        '1. Push app.py, dt-core/main.py, dt-core/human_queue.py, and '
        'install-decision-tree-integration.sh to GitHub.\n'
        '2. Run this once in the Raspberry Pi terminal:\n' + command + '\n'
        '3. The Android email app remains unchanged. Incoming dt-in email questions '
        'will wait for a human answer in Network Assistant, and the existing dt-out '
        'email sender will send the answer.'
    )


def answer(prompt):
    text = prompt.strip()
    low = re.sub(r'\s+', ' ', text.lower())
    if not text:
        return 'Type a question or command first.', clickable_links_html()


    if low in {'decision tree update help', 'decision integration help', 'email integration help'}:
        return decision_tree_github_help_text(), clickable_links_html()

    if low in {'pending questions', 'list pending questions', 'decision questions', 'questions waiting'}:
        return pending_questions_text(), clickable_links_html()
    if low in {'decision queue status', 'question queue status', 'email question status'}:
        return decision_queue_status_text(), clickable_links_html()
    match = re.fullmatch(r'(?:open|show|read) question\s+(\d+)', low)
    if match:
        return open_question_text(int(match.group(1))), clickable_links_html()
    match = re.match(r'answer question\s+(\d+)\s+(.+)', text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return answer_question_text(int(match.group(1)), match.group(2)), clickable_links_html()
    if low.startswith('answer question'):
        return 'Use: answer question NUMBER YOUR ANSWER', clickable_links_html()

    adventure_reply, missing_room = adventure_command(text)
    if adventure_reply:
        if missing_room:
            update_message, changed = check_github_updates()
            if changed:
                return adventure_reply + '\n\n' + update_message + ' Retrying after the automatic restart may reveal a newly added room.', clickable_links_html()
            return adventure_reply + '\n\n' + update_message, clickable_links_html()
        return adventure_reply, clickable_links_html()

    if low in {'test github update', 'github update test', 'update test'}:
        return 'GitHub update test passed. This command exists only in version 7.606.0 or newer.', clickable_links_html()

    if low in {'permission repair log', 'repair log', 'permission log', 'update permission log', 'read repair log', 'show repair log'}:
        return permission_repair_log_text(), clickable_links_html()
    if low in {'update help', 'github update help', 'how to update', 'how do i update', 'engage github update', 'trigger github update'}:
        return github_update_help_text(), clickable_links_html()

    if low in {'version', 'what version', 'version number'} or 'version number' in low:
        return f"Current version: {APP_VERSION}\nRepository: https://github.com/{CONFIG.get('github_repo')}\nBranch: {CONFIG.get('github_branch')}", clickable_links_html()
    if low in {'check updates', 'update check', 'check github', 'update from github'}:
        message, _ = check_github_updates()
        return message, clickable_links_html()
    if low in {'check netnut', 'scan netnut', 'netnut check', 'scan network for netnut'}:
        return check_netnut(), clickable_links_html()
    if low in {'local links', 'links', 'show links', 'clickable links'}:
        return 'Useful San Diego and network-related links are shown below.', clickable_links_html()
    if low in {'simple check', 'simple checks', 'check internet', 'connection check'}:
        return simple_check(), clickable_links_html()
    if 'system status' in low or low == 'status':
        return system_status_text(), clickable_links_html()
    if low in {'list sources', 'show sources', 'sources'}:
        sources = load_sources()
        lines = [f"- {source.get('name')} [{source.get('protocol')}]\n  {source.get('url')}\n  {source.get('description', '')}" for source in sources]
        return 'Saved information sources:\n\n' + ('\n\n'.join(lines) if lines else 'No sources configured.'), clickable_links_html()
    if low.startswith(('fetch ', 'read ', 'get ', 'check source ')):
        name = re.sub(r'^(fetch|read|get|check source)\s+', '', low).strip()
        source = find_source(name)
        if source:
            return safe_fetch_source(source), clickable_links_html()
        update_message, changed = check_github_updates()
        if changed:
            return f"I could not find source '{name}' locally. {update_message} Retry the fetch after restart.", clickable_links_html()
        return f"I could not find source '{name}'. Ask 'list sources'. {update_message}", clickable_links_html()

    update_message, changed = check_github_updates()
    normal = (
        'I am Network Assistant AI. Try:\n'
        '- decision tree update help\n- pending questions\n- open question NUMBER\n- answer question NUMBER YOUR ANSWER\n- decision queue status\n- version\n- check updates\n- update help\n- permission repair log\n- check netnut\n- local links\n- simple check\n'
        '- system status\n- list sources\n- fetch example\n- fetch crime report\n'
        '- fetch power outages\n- fetch news report\n- fetch environmental factors\n'
        '- look\n- open mailbox\n- take leaflet\n- inventory\n- reset game\n'
        '- north, south, east, or west'
    )
    if changed:
        return update_message + '\n\nThe local files were updated. Retry your command after the automatic restart.\n\n' + normal, clickable_links_html()
    return normal + '\n\nGitHub update check: ' + update_message, clickable_links_html()


def restart_process():
    time.sleep(0.8)
    os.execv(sys.executable, [sys.executable, str(APP_PATH)])


class Handler(http.server.BaseHTTPRequestHandler):
    def allowed(self):
        allowed = CONFIG.get('allowed_clients', ['*'])
        return '*' in allowed or self.client_address[0] in allowed

    def send_body(self, body, code=200, content_type='text/html'):
        raw = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_HEAD(self):
        self.send_response(200 if self.allowed() else 403)
        self.end_headers()

    def do_GET(self):
        if not self.allowed():
            self.send_body('Access denied.', 403, 'text/plain')
            return
        self.render_page('', 'Ask: system status, simple check, check netnut, list sources, fetch power outages, or look.')

    def do_POST(self):
        global RESTART_REQUESTED
        if not self.allowed():
            self.send_body('Access denied.', 403, 'text/plain')
            return
        length = min(int(self.headers.get('Content-Length', '0')), 20000)
        raw = self.rfile.read(length).decode('utf-8', errors='replace')
        form = urllib.parse.parse_qs(raw)
        prompt = form.get('prompt', [''])[0]
        reply, links = answer(prompt)
        self.render_page(prompt, reply, links)
        if RESTART_REQUESTED:
            RESTART_REQUESTED = False
            threading.Thread(target=restart_process, daemon=True).start()

    def log_message(self, fmt, *args):
        print(f'{self.client_address[0]} - {fmt % args}')

    def render_page(self, prompt='', reply='', links=''):
        stats = all_stats()
        page = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>{esc(CONFIG.get('app_name', 'Network Assistant AI Console'))}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1050px;margin:24px auto;padding:0 16px;background:#f6f6f6;color:#111}}
.card{{background:#fff;border:1px solid #ddd;border-radius:12px;padding:16px;margin:14px 0}}
textarea{{width:100%;min-height:115px;box-sizing:border-box;padding:10px;font-size:16px}}
button{{padding:10px 14px;border-radius:8px;border:1px solid #777;cursor:pointer;margin:8px 4px 0 0}}
pre{{white-space:pre-wrap;background:#111;color:#eee;padding:12px;border-radius:8px;overflow-x:auto}}
a{{display:inline-block;margin:4px 10px 4px 0}} .small{{color:#555;font-size:14px}}
</style>
<script>
function copyAnswer(){{navigator.clipboard.writeText(document.getElementById('answerbox').innerText).then(()=>document.getElementById('copymsg').innerText='Copied.').catch(()=>document.getElementById('copymsg').innerText='Copy failed.')}}
function askPreset(q){{document.getElementById('prompt').value=q;document.getElementById('askform').submit();}}
</script></head><body>
<h1>{esc(CONFIG.get('ai_display_name', 'Network Assistant AI'))}</h1>
<p class="small">Version {esc(APP_VERSION)}. CPU {esc(stats['cpu_percent'])}%. Memory {esc(stats['memory']['used_percent'])}%.</p>
<div class="card"><form id="askform" method="post"><label for="prompt"><b>Ask Network Assistant AI</b></label>
<textarea id="prompt" name="prompt" placeholder="Ask: check netnut, system status, list sources, fetch power outages, look">{esc(prompt)}</textarea><br>
<button type="submit">Ask</button><button type="button" onclick="askPreset('system status')">System status</button>
<button type="button" onclick="askPreset('simple check')">Simple check</button><button type="button" onclick="askPreset('check netnut')">Check NetNut</button>
<button type="button" onclick="askPreset('local links')">Local links</button><button type="button" onclick="askPreset('list sources')">Sources</button>
<button type="button" onclick="askPreset('look')">Look</button></form></div>
<div class="card"><h2>Answer</h2><button onclick="copyAnswer()">Copy answer</button> <span id="copymsg" class="small"></span>
<pre id="answerbox">{esc(reply)}</pre><div>{links}</div></div>
<div class="card small">Commands: decision tree update help. pending questions. open question NUMBER. answer question NUMBER YOUR ANSWER. decision queue status. version. check updates. update help. permission repair log. check netnut. local links. simple check. system status. list sources. fetch example. fetch crime report. fetch power outages. fetch news report. fetch environmental factors. look. open mailbox. take leaflet. inventory. reset game. north. south. east. west.</div>
</body></html>'''
        self.send_body(page)


if __name__ == '__main__':
    APP_DIR.mkdir(parents=True, exist_ok=True)
    host = CONFIG.get('bind_host', '0.0.0.0')
    port = int(CONFIG.get('port', 80))
    server = http.server.ThreadingHTTPServer((host, port), Handler)
    print(f'Serving {CONFIG.get("app_name", "Network Assistant AI Console")} version {APP_VERSION} on http://{host}:{port}/')
    server.serve_forever()
