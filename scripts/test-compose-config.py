"""Validate Compose topology using synthetic files only, without starting services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    app = work / 'app.env'
    tunnel = work / 'tunnel.env'
    ca = work / 'ca.pem'
    app.write_text('SECRET_KEY=synthetic-configuration-only-not-for-deployment\nDATABASE_PASSWORD=synthetic-only\n')
    tunnel.write_text('TUNNEL_TOKEN=synthetic-token-not-connected\n')
    ca.write_text('synthetic-placeholder-never-connected\n')
    for path in (app, tunnel, ca):
        path.chmod(0o600)
    env = {**os.environ, 'PORTAL_IMAGE': 'portal-medicalimages:0.1.0-compose-check',
           'PORTAL_PRODUCTION_ENV_FILE': str(app), 'PORTAL_TUNNEL_ENV_FILE': str(tunnel),
           'PORTAL_DATABASE_CA_FILE': str(ca), 'PORTAL_STAGING_ENV_FILE': str(app),
           'DATABASE_PASSWORD': 'synthetic-only'}
    def configuration(*files):
        command = ['docker', 'compose']
        for file in files:
            command.extend(['-f', str(root / 'deploy' / file)])
        result = subprocess.run(command + ['config', '--format', 'json'], env=env,
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)
    production = configuration('compose.production.yml')
    assert set(production['services']) == {'web', 'cloudflared'}
    web, connector = (production['services'][name] for name in ('web', 'cloudflared'))
    assert not web.get('ports') and not connector.get('ports')
    assert 'TUNNEL_TOKEN' not in web['environment']
    assert 'SECRET_KEY' not in connector['environment']
    assert connector['environment']['TUNNEL_TOKEN'] == 'synthetic-token-not-connected'
    assert web['environment']['DATABASE_SSLMODE'] == 'verify-full'
    assert web['environment']['DATABASE_SSLROOTCERT'] == '/run/certs/database-ca.pem'
    assert web['environment']['TRUST_PROXY_HTTPS'] == 'true'
    assert production['networks']['application']['internal'] is True
    assert set(web['networks']) & set(connector['networks']) == {'application'}
    assert connector['image'].startswith('cloudflare/cloudflared:2026.10.7@sha256:')
    assert web['read_only'] and connector['read_only']
    setup = configuration('compose.production.yml', 'compose.production.setup.yml')
    assert next(v for v in setup['services']['web']['volumes'] if v['target'] == '/app/.local/static').get('read_only', False) is False
    preview = configuration('compose.staging.yml')
    assert set(preview['services']) == {'web', 'db'}
    assert not preview['services']['db'].get('ports')
    assert preview['services']['web']['ports'][0]['host_ip'] == '127.0.0.1'
    assert preview['services']['web']['environment']['DATABASE_NAME'] == 'portal_staging'
    assert 'alpha.4' not in preview['services']['web']['image']
    configuration('compose.staging.yml', 'compose.setup.yml')
print('Compose topology, isolation and setup overlays passed with synthetic configuration. No services started.')
