from unittest import skipUnless
from pathlib import Path
from django.test import SimpleTestCase


class DeploymentExampleTests(SimpleTestCase):
    @skipUnless((Path(__file__).resolve().parents[1] / '.env.example').exists(), 'Reference excluded from runtime image')
    def test_env_reference_has_names_but_no_values(self):
        root = Path(__file__).resolve().parents[1]
        lines = [line for line in (root / '.env.example').read_text().splitlines()
                 if line and not line.startswith('#')]
        self.assertGreater(len(lines), 40)
        self.assertTrue(all(line.endswith('=') and line.count('=') == 1 for line in lines))
        self.assertIn('TUNNEL_TOKEN=', lines)
        self.assertIn('PORTAL_DATABASE_CA_FILE=', lines)
