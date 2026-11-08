"""Exercise failure propagation in the deployment archive step without Docker."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class RuntimeArtifactTests(unittest.TestCase):
    def test_failed_docker_save_cannot_produce_a_checksummed_artifact(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/ci.yml').read_text()
        step = workflow.split('      - name: Export the exact audited runtime on next\n', 1)[1].split('      - uses:', 1)[0]
        self.assertIn('        shell: bash', step)
        script = '\n'.join(line[10:] for line in step.split('        run: |\n', 1)[1].splitlines())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            fake = path / 'docker'
            fake.write_text('#!/bin/sh\nif [ "$1" = save ]; then exit 7; fi\nif [ "$1" = image ]; then echo "[]"; fi\nexit 0\n')
            fake.chmod(0o700)
            result = subprocess.run(['bash', '-e', '-c', script], cwd=path, env={**os.environ, 'PATH': str(path) + ':' + os.environ['PATH'], 'GITHUB_SHA': '0' * 40}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((path / 'runtime-artifact/SHA256SUMS').exists())
