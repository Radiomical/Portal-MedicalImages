"""Keep the blank inventory and operator reference aligned with runtime inputs."""
import ast
from pathlib import Path
import re
from unittest import skipUnless
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


@skipUnless((ROOT / '.env.example').exists(), 'Operator reference excluded from runtime image')
class ConfigurationReferenceTests(SimpleTestCase):
    def test_runtime_inputs_have_inventory_and_per_variable_reference(self):
        names = set()
        for path in (ROOT / 'portal').glob('*.py'):
            if path.name.startswith('settings_test') or path.name == 'settings_ci_postgres.py':
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args or not isinstance(node.args[0], ast.Constant):
                    continue
                name = node.args[0].value
                if not isinstance(name, str):
                    continue
                # settings uses os.environ.get, env_bool; email_config receives
                # the environment mapping explicitly. wsgi/asgi use setdefault.
                if ((isinstance(node.func, ast.Name) and node.func.id == 'env_bool') or
                    (isinstance(node.func, ast.Attribute) and node.func.attr in {'get', 'setdefault'} and
                     ast.unparse(node.func.value) in {'os.environ', 'environ'})):
                    names.add(name)
        for path in (ROOT / 'deploy').glob('compose*.yml'):
            names.update(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', path.read_text()))
        names.update({'PORTAL_COMPOSE_ENV_FILE', 'PGOPTIONS', 'SSL_CERT_FILE'})
        inventory = {line.split('=', 1)[0] for line in (ROOT / '.env.example').read_text().splitlines()
                     if line and not line.startswith('#')}
        reference = (ROOT / 'deploy/CONFIGURATION.md').read_text()
        documented = set(re.findall(r'^\| `([A-Z][A-Z0-9_]*)` \|', reference, re.M))
        self.assertGreater(len(names), 50)
        self.assertEqual(names - inventory, set(), 'Runtime inputs missing from .env.example')
        self.assertEqual(inventory, documented, 'Every inventory name needs its own reference row')

    def test_examples_contain_no_credential_values(self):
        lines = (ROOT / '.env.example').read_text().splitlines()
        for line in lines:
            if line and not line.startswith('#'):
                self.assertTrue(line.endswith('=') and line.count('=') == 1)
