import requests
import time

BASE = 'http://localhost:8888'


def health():
    r = requests.get(f'{BASE}/health', timeout=5)
    r.raise_for_status()
    return r.json()


def run_agent(session_id: str):
    payload = {
        'message': 'Create a minimal hello world in C',
        'session_id': session_id,
        'working_dir': '.',
        'max_iterations': 2,
        'temperature': 0.1,
        'max_tokens': 128,
    }
    r = requests.post(f'{BASE}/agent/run', json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


if __name__ == '__main__':
    print('health:', health())
    a = run_agent('reconnect-test-a')
    time.sleep(1)
    b = run_agent('reconnect-test-b')
    print('a.session_id=', a.get('session_id'))
    print('b.session_id=', b.get('session_id'))
    sessions = requests.get(f'{BASE}/agent/sessions', timeout=5).json().get('sessions', [])
    print('sessions:', [s['session_id'] for s in sessions])
