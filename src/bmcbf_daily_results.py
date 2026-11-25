"""Read existing BMCBF result logs without running tasks or importing its code."""
from datetime import datetime
from pathlib import Path
import re

LINE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - (.*?) - (INFO|WARNING|ERROR) - (.*)$')


def daily_summary(path, now=None):
    now = now or datetime.now()
    rows = set()
    promotions = []
    for file in [Path(str(path)+'.2'), Path(str(path)+'.1'), Path(path)]:
        try:
            with file.open('rb') as stream:
                stream.seek(max(0, file.stat().st_size - 4_000_000))
                text = stream.read().decode('utf-8', errors='replace')
        except OSError:
            continue
        for line in text.splitlines():
            match = LINE.match(line)
            if match:
                promoted = re.search(r"Updated promotion state after live promotion for '(.*)'\. Post ID", match[4])
                if promoted:
                    promotions.append((match[1], promoted[1]))
            if match and match[1].startswith(now.strftime('%Y-%m-%d')):
                rows.add(match.groups())
    if not rows:
        return None
    rows = sorted(rows)
    latest_mail = None
    posts = {}
    latest_promotion = None
    scraper_runs = []
    errors = {}
    summaries = 0
    locations = set()
    changed_locations = set()
    mail_count = None
    actionable = 0
    for stamp, module, level, message in rows:
        clock = stamp[11:16]
        if module == 'actions.email.unread_summarizer':
            found = re.search(r'Fetched (\d+) most recent unread emails\.', message)
            if found:
                mail_count = int(found[1])
                latest_mail = f'Email {clock}: {mail_count} unread found at last check.'
            if message.strip() == 'LLM classified as Action Required.':
                actionable += 1
            if message == 'No unread emails found.':
                latest_mail = f'Email {clock}: no unread mail found.'
            if message == 'Discord summary notification sent successfully.':
                summaries += 1
                latest_mail = f'Email {clock}: new summary sent to Discord.'
        if module.startswith('actions.social_media.'):
            for platform, signal in [('Facebook','Facebook post successful:'),('Threads','Threads post successful:'),('Bluesky','Successfully posted to Bluesky.')]:
                if signal in message:
                    posts[platform] = posts.get(platform, 0) + 1
            if message.startswith('No recent published WordPress posts found'):
                latest_promotion = f'Promotion check {clock}: no new posts found.'
        scraper = re.search(r'^(.*?) completed with status: (\w+)', message)
        if scraper and ('scraper' in module or 'scrape' in module):
            scraper_runs.append((clock, scraper[1], scraper[2]))
        processed = re.search(r'Successfully processed location ID (\d+) for expected map ID\.',message)
        if module.endswith('map_location_monitor') and processed:
            locations.add(processed[1])
        changed = re.search(r'Successfully updated WP Maps location ID (\d+)\.', message)
        if changed:
            changed_locations.add(changed[1])
        if level == 'ERROR':
            # Export only source names/times; log bodies may contain private data.
            errors[module] = clock
    lines = ['Today ' + now.strftime('%b ') + str(now.day)]
    if summaries or actionable:
        mail_line = f'{summaries} email summaries today; {actionable} action-required results'
    elif mail_count is not None and mail_count > 0:
        mail_line = f'{mail_count} unread at last check; no summary delivered yet'
    elif latest_mail:
        mail_line = 'No email found today'
    else:
        mail_line = 'Email status unavailable'
    lines.append('- ' + mail_line)
    lines.append(f'- {len(changed_locations)} locations changed ({len(locations)} checked)')
    lines.append('- Today\'s events: unavailable')
    if promotions:
        stamp,title = max(promotions)
        when = datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S').strftime('%b %d %H:%M')
        lines.append(f'- Last article: {title} ({when})')
    else:
        lines.append('- Last article: unavailable')
    return '\n'.join(lines)
