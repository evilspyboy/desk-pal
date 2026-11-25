"""Dependency-free example sender. Replace demo payloads with your application's state."""
import argparse
import json
import urllib.request


def send(endpoint, app_id, payload, event=None):
    data = dict(payload, app_id=app_id)
    if event: data['event'] = event
    path = 'event' if event else 'heartbeat'
    request = urllib.request.Request(endpoint.rstrip('/')+'/api/v1/'+path,
        data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deskpal', required=True, help='Your Desk-Pal URL, including its port')
    parser.add_argument('--app-id', default='example_app')
    parser.add_argument('--event', help='Omit for a heartbeat; otherwise use an imported event name')
    parser.add_argument('--payload', help='JSON file containing real values from your application')
    args = parser.parse_args()
    if args.payload:
        with open(args.payload, encoding='utf-8') as source: payload = json.load(source)
    else:
        payload = {'status': 'healthy', 'summary': 'Demo update from the integration example',
                   'job_name': 'Example job', 'success': True, 'demo': True}
    print(send(args.deskpal, args.app_id, payload, args.event))
